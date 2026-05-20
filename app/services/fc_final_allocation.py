
import pandas as pd
from app.services.fc_planning import calculate_fc_plan
from app.services.fc_transfer import calculate_fc_transfers
from app.services.file_cache import get, get_excel_sheet


# ===============================================================
# FINAL FC ALLOCATION ENGINE
# ===============================================================

def calculate_final_allocation(
    replenish_weeks: int = 8,
    channel: str = "All",
    account: str = "Nexlev"
) -> pd.DataFrame:



    # ==========================================================
    # STEP 1 — LOAD FC PLANNING DATA
    # ==========================================================

    df_plan = calculate_fc_plan(
        replenish_weeks=replenish_weeks,
        channel=channel,
        account=account
    )

    if df_plan is None or df_plan.empty:
        return pd.DataFrame()
    
    # ADD HERE
    if "model" not in df_plan.columns:
       df_plan["model"] = "-"

    required_cols = [
        "sku",
        "fulfillment_center",
        "weekly_velocity",
        "fc_inventory",
        "required_units",
        "fc_shortfall"
    ]

    for col in required_cols:
        if col not in df_plan.columns:
            df_plan[col] = 0

    numeric_cols = [
        "weekly_velocity",
        "fc_inventory",
        "required_units",
        "fc_shortfall"
    ]

    for col in numeric_cols:
        df_plan[col] = pd.to_numeric(
            df_plan[col],
            errors="coerce"
        ).fillna(0)

    # Normalize SKU
    df_plan["sku"] = (
        df_plan["sku"]
        .astype(str)
        .str.strip()
        .str.upper()
    )
    # ==========================================================
    # STEP 2 — LOAD TRANSFER DATA
    # (Fossil skips transfers — direct dispatch from Mother Warehouse)
    # ==========================================================

    df_transfer = None
    if account.lower() != "fossil":
        df_transfer = calculate_fc_transfers(
            replenish_weeks=replenish_weeks,
            account=account
        )

    if df_transfer is None or df_transfer.empty:
        df_plan["transfer_in"] = 0
    else:
        df_transfer = df_transfer.rename(columns={
            "Merchant SKU": "sku",
            "SKU": "sku",
            "To FC": "to_fc",
            "Transfer Qty": "transfer_qty"
        })

        df_transfer["sku"] = (
            df_transfer["sku"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        df_transfer["transfer_qty"] = pd.to_numeric(
            df_transfer.get("transfer_qty", 0),
            errors="coerce"
        ).fillna(0)

        transfer_in = (
            df_transfer
            .groupby(["sku", "to_fc"], as_index=False)
            .agg(transfer_in=("transfer_qty", "sum"))
        )

        df_plan = df_plan.merge(
            transfer_in,
            left_on=["sku", "fulfillment_center"],
            right_on=["sku", "to_fc"],
            how="left"
        )

        df_plan["transfer_in"] = df_plan["transfer_in"].fillna(0)

        if "to_fc" in df_plan.columns:
            df_plan.drop(columns=["to_fc"], inplace=True)

    # ==========================================================
    # STEP 3 — TARGET COVER CALCULATION
    # ==========================================================

    df_plan["target_cover_units"] = (
        df_plan["weekly_velocity"] * float(replenish_weeks)
    )
   
    df_plan["total_units_sold"] = df_plan["total_units_90d"]

    df_plan["post_transfer_stock"] = (
        df_plan["fc_inventory"] + df_plan["transfer_in"]
    )
    

    # ==========================================================
    # STEP 4 — ADJUST SHORTFALL
    # ==========================================================

    df_plan["adjusted_shortfall"] = (
        df_plan["target_cover_units"] -
        df_plan["post_transfer_stock"]
    ).clip(lower=0)

    df_plan["send_qty"] = df_plan["adjusted_shortfall"]
    df_plan["original_required_units"] = df_plan["adjusted_shortfall"]

    # DEBUG — check FBA66963 DEL5 at adjusted_shortfall step
    if account.lower() == "fossil" and "sku" in df_plan.columns:
        d = df_plan[(df_plan["sku"].astype(str).str.contains("66963", na=False)) & 
                    (df_plan["fulfillment_center"].astype(str).str.upper() == "DEL5")]
        if len(d):
            r = d.iloc[0]
            print(f"🔍 STEP4 FBA66963/DEL5: velocity={r['weekly_velocity']:.2f}, fc_inv={r['fc_inventory']:.0f}, target={r['target_cover_units']:.1f}, shortfall={r['adjusted_shortfall']:.1f}, send_qty={r['send_qty']:.1f}")
    

    # NOW create expected_units
    df_plan["expected_units"] = df_plan["original_required_units"]

    # ==========================================================
    # FOSSIL EXCEPTION — no governance, no velocity flags,
    # AMPM stock from "Fossil SOH" column in master sheet
    # ==========================================================
    if account.lower() == "fossil":
        fossil_master = get_excel_sheet("Fossil Replenishment/Fossil Replenishment.xlsx", "Sheet1")
        fossil_master.columns = fossil_master.columns.str.strip()
        fossil_master = fossil_master.rename(columns={
            "SKU": "sku",
            "Item No": "model",
            "ASIN": "asin",
            "Category": "category",
            "Fossil Assortment": "fossil_assortment",
            "Assortment Type": "assortment",
            "Fossil SOH": "ampm_inventory",
        })
        fossil_master["sku"] = fossil_master["sku"].astype(str).str.strip().str.upper()
        fossil_master["ampm_inventory"] = pd.to_numeric(fossil_master["ampm_inventory"], errors="coerce").fillna(0)

        keep_cols = [c for c in ["sku", "model", "asin", "category", "assortment", "fossil_assortment", "ampm_inventory"] if c in fossil_master.columns]
        fossil_master = fossil_master[keep_cols]

        df_plan = df_plan.merge(fossil_master, on="sku", how="left", suffixes=("", "_fm"))

        # model from master takes priority
        if "model_fm" in df_plan.columns:
            df_plan["model"] = df_plan["model_fm"].combine_first(df_plan["model"])
            df_plan.drop(columns=["model_fm"], inplace=True)

        df_plan["model"]          = df_plan.get("model", pd.Series("-")).fillna("-")
        df_plan["asin"]           = df_plan.get("asin", pd.Series("-")).fillna("-")
        df_plan["category"]       = df_plan.get("category", pd.Series("-")).fillna("-")
        df_plan["assortment"]     = df_plan.get("assortment", pd.Series("-")).fillna("-")
        df_plan["fossil_assortment"] = df_plan.get("fossil_assortment", pd.Series("-")).fillna("-")
        df_plan["hazmat_type"]   = "-"
        df_plan["master_carton"] = "24"   # default 24 for Fossil
        df_plan["remarks"]       = ""
        df_plan["ampm_inventory"]= pd.to_numeric(df_plan.get("ampm_inventory", 0), errors="coerce").fillna(0)

        # No governance — send_qty = adjusted_shortfall as-is
        df_plan["ixd_flag"]       = "Non-IXD"   # treat all as non-IXD (no 35% cap)
        df_plan["master_carton"]  = "-"
        df_plan["listing_status"] = "-"
        df_plan["fill_pct"]       = 100.0        # no governance reduction
        df_plan["velocity_flag"]  = "OK"         # no SHORT flagging for Fossil
        df_plan["allocation_logic"] = "send_qty = max(0, weekly_velocity * replenish_weeks - (fc_inventory + transfer_in))"
        df_plan["coverage_gap_units"] = df_plan["adjusted_shortfall"]

        # ==========================================================
        # FOSSIL IN-TRANSIT + OPEN PO
        # ==========================================================
        try:
            po_df = get_excel_sheet("Fossil Replenishment/In-Transit_Open_PO_Fossil.xlsx", "Sheet1")
            po_df.columns = po_df.columns.str.strip()

            po_df["Item No"] = po_df["Item No"].astype(str).str.strip().str.upper()
            po_df["FC"]      = po_df["FC"].astype(str).str.strip().str.upper()
            po_df["remark"]  = po_df["PO fulfillment Remark"].astype(str).str.strip()

            po_df["packing_list_qty"] = pd.to_numeric(po_df["Packing List Qty"], errors="coerce").fillna(0)
            po_df["po_qty"]           = pd.to_numeric(po_df["PO Qty"], errors="coerce").fillna(0)

            # In-Transit: use Packing List Qty
            in_transit = (
                po_df[po_df["remark"] == "In-Transit"]
                .groupby(["Item No", "FC"], as_index=False)
                .agg(in_transit_qty=("packing_list_qty", "sum"))
            )

            # Open PO: use PO Qty
            open_po = (
                po_df[po_df["remark"] == "Open PO"]
                .groupby(["Item No", "FC"], as_index=False)
                .agg(open_po_qty=("po_qty", "sum"))
            )

            # df_plan uses "model" as Item No for Fossil (mapped from Item No column)
            df_plan["item_no"] = df_plan["model"].astype(str).str.strip().str.upper()
            df_plan["fc_upper"] = df_plan["fulfillment_center"].astype(str).str.strip().str.upper()

            df_plan = df_plan.merge(
                in_transit, left_on=["item_no", "fc_upper"], right_on=["Item No", "FC"], how="left"
            ).drop(columns=["Item No", "FC"], errors="ignore")

            df_plan = df_plan.merge(
                open_po, left_on=["item_no", "fc_upper"], right_on=["Item No", "FC"], how="left"
            ).drop(columns=["Item No", "FC"], errors="ignore")

            df_plan["in_transit_qty"] = pd.to_numeric(df_plan["in_transit_qty"], errors="coerce").fillna(0).astype(int)
            df_plan["open_po_qty"]    = pd.to_numeric(df_plan["open_po_qty"], errors="coerce").fillna(0).astype(int)
            df_plan.drop(columns=["item_no", "fc_upper"], inplace=True)

            # Recalculate send_qty deducting In-Transit and Open PO
            df_plan["send_qty"] = (
                df_plan["send_qty"] - df_plan["in_transit_qty"] - df_plan["open_po_qty"]
            ).clip(lower=0)
            df_plan["allocation_logic"] = "send_qty = max(0, weekly_velocity * replenish_weeks - ledger_stock - in_transit - open_po)"

            # Add missing SKU+FC rows from In-Transit AND Open PO file (no sales/ledger history)
            po_df["item_no_upper"] = po_df["Item No"].astype(str).str.strip().str.upper()
            po_df["fc_upper"]      = po_df["FC"].astype(str).str.strip().str.upper()

            # Build ledger lookup for skeleton rows — so fc_inventory reflects actual stock
            try:
                from app.services.fc_planning import load_fc_data
                _, ledger_raw = load_fc_data("fossil")
                ledger_raw = ledger_raw[ledger_raw["Disposition"] == "SELLABLE"].copy()
                ledger_raw["MSKU"] = ledger_raw["MSKU"].astype(str).str.strip().str.upper()
                ledger_raw["MSKU"] = ledger_raw["MSKU"].str.replace(r"^FB[^A]", "FBA", regex=True)
                ledger_raw["Location"] = ledger_raw["Location"].astype(str).str.strip().str.upper()
                ledger_raw["Ending Warehouse Balance"] = pd.to_numeric(ledger_raw["Ending Warehouse Balance"], errors="coerce").fillna(0)
                # Build SKU→model mapping from fossil master
                sku_to_model = fossil_master.set_index("sku")["model"].to_dict() if "sku" in fossil_master.columns else {}
                ledger_raw["model_upper"] = ledger_raw["MSKU"].map(sku_to_model).fillna("").astype(str).str.upper()
                ledger_lookup = (
                    ledger_raw.groupby(["model_upper", "Location"], as_index=False)
                    .agg(fc_inventory=("Ending Warehouse Balance", "sum"))
                )
            except Exception as e:
                print(f"⚠️ Ledger lookup for skeleton rows failed: {e}")
                ledger_lookup = pd.DataFrame(columns=["model_upper", "Location", "fc_inventory"])

            # Get SKU+FC combos already in df_plan
            plan_keys = set(zip(
                df_plan["model"].astype(str).str.strip().str.upper(),
                df_plan["fulfillment_center"].astype(str).str.strip().str.upper()
            ))

            # Aggregate In-Transit and Open PO per Item No + FC
            it_rows = (
                po_df[po_df["remark"] == "In-Transit"]
                .groupby(["item_no_upper", "fc_upper"], as_index=False)
                .agg(in_transit_qty=("packing_list_qty", "sum"))
            )
            op_rows = (
                po_df[po_df["remark"] == "Open PO"]
                .groupby(["item_no_upper", "fc_upper"], as_index=False)
                .agg(open_po_qty=("po_qty", "sum"))
            )

            # Merge In-Transit and Open PO into one view per Item No + FC
            po_combined = it_rows.merge(op_rows, on=["item_no_upper", "fc_upper"], how="outer").fillna(0)
            po_combined["in_transit_qty"] = po_combined["in_transit_qty"].astype(int)
            po_combined["open_po_qty"] = po_combined["open_po_qty"].astype(int)

            # Find rows not already in df_plan
            missing = po_combined[
                ~po_combined.apply(lambda r: (r["item_no_upper"], r["fc_upper"]) in plan_keys, axis=1)
            ]

            if len(missing) > 0:
                # Build skeleton rows for missing SKU+FC
                fossil_master_lookup = fossil_master.set_index("model") if "model" in fossil_master.columns else fossil_master.rename(columns={"Item No": "model"}).set_index("model")
                new_rows = []
                for _, row in missing.iterrows():
                    model = row["item_no_upper"]
                    fc    = row["fc_upper"]
                    if model in fossil_master_lookup.index:
                        mr_raw = fossil_master_lookup.loc[model]
                        # Handle duplicate models — take first row
                        if isinstance(mr_raw, pd.DataFrame):
                            mr = mr_raw.iloc[0].to_dict()
                        else:
                            mr = mr_raw.to_dict()
                    else:
                        mr = {}
                    def safe(val, default=""):
                        import math
                        if val is None: return default
                        try:
                            if isinstance(val, float) and math.isnan(val): return default
                        except: pass
                        return val if val != "" else default
                    # Look up actual ledger inventory for this model+FC
                    ledger_inv = 0
                    if not ledger_lookup.empty:
                        match = ledger_lookup[
                            (ledger_lookup["model_upper"] == model) &
                            (ledger_lookup["Location"] == fc)
                        ]
                        if len(match):
                            ledger_inv = int(match["fc_inventory"].sum())
                    new_rows.append({
                        "model":              model,
                        "sku":                safe(mr.get("sku", ""), ""),
                        "asin":               safe(mr.get("asin", ""), ""),
                        "category":           safe(mr.get("category", "-"), "-"),
                        "assortment":         safe(mr.get("assortment", "-"), "-"),
                        "fossil_assortment":  safe(mr.get("fossil_assortment", "-"), "-"),
                        "listing_status":     "-",
                        "ampm_inventory":     0,
                        "fulfillment_center": fc,
                        "weekly_velocity":    0,
                        "total_units_sold":   0,
                        "fc_inventory":       ledger_inv,
                        "transfer_in":        0,
                        "target_cover_units": 0,
                        "post_transfer_stock":ledger_inv,
                        "coverage_gap_units": 0,
                        "send_qty":           0,
                        "expected_units":     0,
                        "fill_pct":           0,
                        "velocity_flag":      "NO_SALES",
                        "ixd_flag":           "-",
                        "hazmat_type":        "-",
                        "master_carton":      "24",
                        "remarks":            "",
                        "allocation_logic":   "in_transit_or_open_po_only",
                        "in_transit_qty":     int(row["in_transit_qty"]),
                        "open_po_qty":        int(row["open_po_qty"]),
                    })
                if new_rows:
                    df_plan = pd.concat([df_plan, pd.DataFrame(new_rows)], ignore_index=True)

        except Exception as e:
            print("⚠️ Fossil In-Transit/Open PO load error:", e)
            df_plan["in_transit_qty"] = 0
            df_plan["open_po_qty"]    = 0

        fossil_final = df_plan[[
            "model", "sku", "asin", "category", "assortment", "fossil_assortment", "listing_status", "ampm_inventory",
            "fulfillment_center", "weekly_velocity", "total_units_sold", "fc_inventory",
            "transfer_in", "target_cover_units", "post_transfer_stock", "coverage_gap_units",
            "send_qty", "expected_units", "fill_pct", "velocity_flag",
            "ixd_flag", "hazmat_type", "master_carton", "remarks", "allocation_logic",
            "in_transit_qty", "open_po_qty",
        ]].copy()

        # DEBUG — check send_qty before numeric cleanup
        d = fossil_final[fossil_final["sku"].astype(str).str.contains("66963", na=False) & 
                         (fossil_final["fulfillment_center"].astype(str).str.upper()=="DEL5")]
        if len(d):
            print(f"🔍 PRE-CLEANUP FBA66963/DEL5: send_qty={d.iloc[0]['send_qty']}, in_transit={d.iloc[0]['in_transit_qty']}")

        numeric_cleanup_cols = [
            "weekly_velocity", "fc_inventory", "transfer_in", "target_cover_units",
            "post_transfer_stock", "coverage_gap_units", "send_qty", "expected_units",
            "in_transit_qty", "open_po_qty",
        ]
        for col in numeric_cleanup_cols:
            fossil_final[col] = pd.to_numeric(fossil_final[col], errors="coerce").fillna(0)

        fossil_final[numeric_cleanup_cols] = fossil_final[numeric_cleanup_cols].round(0).astype(int)

        for col in ["ixd_flag", "hazmat_type", "category", "asin", "master_carton", "listing_status"]:
            fossil_final[col] = (
                fossil_final[col].astype(str).str.strip()
                .replace({"nan": None, "None": None, "<NA>": None, "": None})
                .fillna("-")
            )

        return fossil_final

    # ==========================================================
    # STEP 5B — HAZMAT GOVERNANCE (35%)  [non-Fossil accounts]
    # ==========================================================

    if account.lower() == "nexlev":
        repl_path = "data/input/replenishment_master_nexlev.xlsx"
        sheet_to_load = "Nexlev"
    elif account.lower() == "viomi":
        repl_path = "data/input/replenishment_master_viomi.xlsx"
        sheet_to_load = "Viomi"
    elif account.lower() == "audio array":
        repl_path = "data/input/Audio Array & WM Replenishment/AA & WM Replenishment.xlsx"
        sheet_to_load = "AA"
    else:
        repl_path = "data/input/Audio Array & WM Replenishment/AA & WM Replenishment.xlsx"
        sheet_to_load = "WM"

    try:
        repl_master = get_excel_sheet(
            repl_path.replace("data/input/", ""),
            sheet_to_load
        )

        repl_master.columns = repl_master.columns.str.strip()

        if account.lower() in ["nexlev", "viomi"]:
            repl_master = repl_master.rename(columns={
                "SKU": "sku",
                "Hazmat/non-Hazmat": "ixd_flag",
                "Hazmat Type": "hazmat_type",
                "Model": "model",
                "Category": "category",
                "ASIN": "asin",
                "Master Carton": "master_carton",
                "Status": "listing_status"
            })
        else:
            repl_master = repl_master.rename(columns={
                "SKU": "sku",
                "Hazmat Type": "ixd_flag",
                "Model": "model",
                "Category": "category",
                "ASIN": "asin",
                "Master Carton": "master_carton"
            })
            if "ixd_flag" not in repl_master.columns:
                repl_master["ixd_flag"] = "IXD"
            repl_master["hazmat_type"] = repl_master["ixd_flag"]

        repl_master["category"] = repl_master.get("category", pd.Series(dtype=str)).fillna("-")

        if "listing_status" not in repl_master.columns:
            repl_master["listing_status"] = "-"

        repl_master = repl_master[
            ["sku", "model", "ixd_flag", "hazmat_type", "category", "asin", "master_carton", "listing_status"]
        ]

        repl_master["sku"] = (
            repl_master["sku"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

    except Exception as e:
        print("⚠️ Excel load failed:", e)

        repl_master = pd.DataFrame(
            columns=["sku", "model", "ixd_flag", "hazmat_type", "category", "asin", "master_carton", "listing_status"]
        )


    df_plan = df_plan.merge(repl_master, on="sku", how="left", suffixes=("", "_y"))


    df_plan["asin"] = df_plan["asin"].fillna("-") if "asin" in df_plan.columns else "-"
    df_plan["master_carton"] = df_plan["master_carton"].fillna("-") if "master_carton" in df_plan.columns else "-"
     
    df_plan["ixd_flag"] = df_plan["ixd_flag"].astype(str)
    df_plan["ixd_flag"] = df_plan["ixd_flag"].replace("nan", None)
    

    if "model_y" in df_plan.columns:
        df_plan["model"] = df_plan["model_y"].combine_first(df_plan.get("model"))
        df_plan.drop(columns=["model_y"], inplace=True)

    df_plan["model"] = df_plan["model"].fillna("-")

    IST_PERCENTAGE = 0.35

    def apply_ist(row):
        raw_flag = row.get("ixd_flag")
        
        flag = str(raw_flag).strip().lower() if raw_flag is not None else ""
        
        if "non-ixd" in flag or "non ixd" in flag:
            return row["send_qty"]

        return row["send_qty"] * IST_PERCENTAGE

    # APPLY GOVERNANCE
    df_plan["send_qty"] = df_plan.apply(apply_ist, axis=1)

    # ==========================================================
# STEP 5C — GOVERNANCE SHORTFALL FLAG
# ==========================================================
    df_plan["governance_fill_ratio"] = 0.0

    mask = df_plan["original_required_units"] > 0

    df_plan.loc[mask, "governance_fill_ratio"] = (
        df_plan.loc[mask, "send_qty"] /
        df_plan.loc[mask, "original_required_units"]
        )
    
    df_plan["governance_fill_ratio"] = (
        df_plan["governance_fill_ratio"]
        .replace([float("inf"), -float("inf")], 0)
        .fillna(0)
        )
    
    df_plan["fill_pct"] = (
        df_plan["governance_fill_ratio"] * 100
        ).round(1)
    
    def governance_flag_logic(row):
        if row["original_required_units"] == 0:
            return "NO_REQUIREMENT"
        elif row["governance_fill_ratio"] <= 0.70:
            return "SHORT_30%+"
        else:
            return "OK"

    df_plan["velocity_flag"] = df_plan.apply(
        governance_flag_logic,
        axis=1
        )

    # ==========================================================
    # STEP 6 — EXPLAINABILITY
    # ==========================================================

    df_plan["allocation_logic"] = (
        "send_qty = max(0, weekly_velocity * replenish_weeks "
        "- (fc_inventory + transfer_in))"
    )

    df_plan["coverage_gap_units"] = (
        df_plan["adjusted_shortfall"]
    )
     
    # =========================
    # AMPM INVENTORY (NEW)
    # =========================

    if account.lower() == "white mulberry":
        ampm_file = "data/input/Inventory_snapshot_WM.xlsx"
    elif account.lower() == "audio array":
        ampm_file = "data/input/Inventory_snapshot_audio_array.xlsx"
    else:
        ampm_file = "data/input/inventory_snapshot_nexlev.xlsx"

    ampm_df = get(ampm_file.replace("data/input/", ""))

    ampm_df.columns = ampm_df.columns.str.lower().str.strip()

    ampm_df = ampm_df[ampm_df["channel"].str.lower() == "ampm"]

    ampm_df["model"] = ampm_df["model"].astype(str).str.strip()
    df_plan["model"] = df_plan["model"].astype(str).str.strip()

    # Case-insensitive model matching — same fix as the Replenishment service.
    # Inventory snapshots have models like "AM-W33 pro" / "AM-C11 PRO" / "AM-C3A"
    # whereas the master uses "AM-W33 Pro" / "AM-C11 Pro" / "AM-C3a". Normalise
    # the inventory's model to the master's canonical casing before the merge,
    # else those SKUs land in the "no match → ampm_inventory = 0" bucket.
    master_models       = set(df_plan["model"].dropna().astype(str).unique())
    master_models_lower = {m.lower(): m for m in master_models}

    def _normalize_inv_model(m):
        m = str(m).strip()
        if not m:
            return m
        if m in master_models:
            return m
        if m.lower() in master_models_lower:
            return master_models_lower[m.lower()]
        # Variant suffix after last '-'  (e.g. "ETC-07-WH" -> "ETC-07")
        parts = m.rsplit("-", 1)
        if len(parts) == 2:
            if parts[0] in master_models:
                return parts[0]
            if parts[0].lower() in master_models_lower:
                return master_models_lower[parts[0].lower()]
        # Bundle descriptor after '('  ("UB-01 (AI-04…)" -> "UB-01")
        base = m.split("(")[0].strip()
        if base in master_models:
            return base
        if base.lower() in master_models_lower:
            return master_models_lower[base.lower()]
        return m

    ampm_df["model"] = ampm_df["model"].apply(_normalize_inv_model)

    ampm_df = ampm_df.groupby("model", as_index=False)["qty"].sum()

    ampm_df = ampm_df.rename(columns={"qty": "ampm_inventory"})

    # merge with main df
    df_plan = df_plan.merge(
        ampm_df,
        on="model",
        how="left"
)

    df_plan["ampm_inventory"] = pd.to_numeric(df_plan["ampm_inventory"], errors="coerce").fillna(0)

    if "category" in df_plan.columns:
        df_plan["category"] = df_plan["category"].fillna("-").astype(str).str.strip().replace("nan", "-")
    else:
        df_plan["category"] = "-"

    if "listing_status" not in df_plan.columns:
        df_plan["listing_status"] = "-"
    # ==========================================================
    # FINAL DATASET
    # ==========================================================

    final_df = df_plan[[
        "model",
        "sku",
        "asin",
        "category",
        "listing_status",
        "ampm_inventory",
        "fulfillment_center",
        "weekly_velocity",
        "total_units_sold",
        "fc_inventory",
        "transfer_in",
        "target_cover_units",
        "post_transfer_stock",
        "coverage_gap_units",
        "send_qty",
        "expected_units",
        "fill_pct",
        "velocity_flag",
        "ixd_flag",
        "hazmat_type",
        "master_carton",
        "allocation_logic"
    ]].copy()

    numeric_cleanup_cols = [
        "weekly_velocity",
        "fc_inventory",
        "transfer_in",
        "target_cover_units",
        "post_transfer_stock",
        "coverage_gap_units",
        "send_qty",
        "expected_units",
    ]


   
    for col in numeric_cleanup_cols:
        final_df[col] = pd.to_numeric(
            final_df[col],
            errors="coerce"
        ).fillna(0)

    
    final_df["ixd_flag"] = (
    final_df["ixd_flag"]
    .astype(str)
    .str.strip()
    .replace({"nan": None, "None": None, "<NA>": None, "": None})
    .fillna("unknown")
)

    final_df["hazmat_type"] = (
    final_df["hazmat_type"]
    .astype(str)
    .str.strip()
    .replace({"nan": None, "None": None, "<NA>": None, "": None})
    .fillna("unknown")
)

    final_df["category"] = (
    final_df["category"]
    .astype(str)
    .str.strip()
    .replace({"nan": None, "None": None, "<NA>": None, "": None})
    .fillna("-")
)

    final_df["asin"] = (
    final_df["asin"]
    .astype(str)
    .str.strip()
    .replace({"nan": None, "None": None, "<NA>": None, "": None})
    .fillna("-")
)

    final_df["master_carton"] = (
    final_df["master_carton"]
    .astype(str)
    .str.strip()
    .replace({"nan": None, "None": None, "<NA>": None, "": None})
    .fillna("-")
)

    final_df["listing_status"] = (
    final_df["listing_status"]
    .astype(str)
    .str.strip()
    .replace({"nan": None, "None": None, "<NA>": None, "": None})
    .fillna("-")
)
    
    final_df[numeric_cleanup_cols] = (
    final_df[numeric_cleanup_cols]
    .round(0)
    .astype(int)
)

    return final_df