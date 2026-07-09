
import pandas as pd
from pathlib import Path
from app.services.fc_planning import calculate_fc_plan
from app.services.fc_transfer import calculate_fc_transfers
from app.services.file_cache import get, get_excel_sheet


# ===============================================================
# FINAL FC ALLOCATION ENGINE
# ===============================================================

def calculate_final_allocation(
    replenish_weeks: int = 8,
    channel: str = "All",
    account: str = "Nexlev",
    sales_window: int = 12,
    from_week: int | None = None,
    to_week:   int | None = None,
) -> pd.DataFrame:



    # ==========================================================
    # STEP 1 — LOAD FC PLANNING DATA
    # ==========================================================

    df_plan = calculate_fc_plan(
        replenish_weeks=replenish_weeks,
        channel=channel,
        account=account,
        sales_window=sales_window,
        from_week=from_week,
        to_week=to_week,
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
        "fc_in_transit",
        "required_units",
        "fc_shortfall"
    ]

    for col in required_cols:
        if col not in df_plan.columns:
            df_plan[col] = 0

    numeric_cols = [
        "weekly_velocity",
        "fc_inventory",
        "fc_in_transit",
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
                # Filter to latest date only — SP-API ledger returns multi-day
                # history; without this fc_inventory over-counts by (n_days)x.
                if "Date" in ledger_raw.columns:
                    ledger_raw["_dt"] = pd.to_datetime(
                        ledger_raw["Date"], errors="coerce", format="%m/%d/%Y"
                    )
                    _miss = ledger_raw["_dt"].isna()
                    if _miss.any():
                        ledger_raw.loc[_miss, "_dt"] = pd.to_datetime(
                            ledger_raw.loc[_miss, "Date"], errors="coerce",
                            format="%d-%m-%Y"
                        )
                    _lat = ledger_raw["_dt"].max()
                    if pd.notna(_lat):
                        ledger_raw = ledger_raw[ledger_raw["_dt"] == _lat].copy()
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
                        "b2b_inventory":      0,
                        "inbound_to_fc":      0,
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
        sheet_to_load = "nexlev"
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

    # AMPM lookup — ASIN primary, SKU fallback, Model fallback (exclusive).
    # Same project standard as CB / WM / replenishment. ASIN-primary anchors
    # on the most stable identity so silent zeros from Model-string drift
    # in the snapshot (e.g. "POS BRACKET" vs "POSS-01") can't happen.
    ampm_df["_asin"]  = ampm_df.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    ampm_df["_sku"]   = ampm_df.get("sku",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    ampm_df["_model"] = ampm_df["model"].astype(str).str.strip().str.lower()

    # ASIN: rows w/ non-empty ASIN
    # SKU: rows w/ non-empty SKU (non-exclusive — catches ASIN-drift cases)
    # Model: rows w/ EMPTY ASIN AND SKU only (exclusive — no dup-Model bleed)
    ampm_by_asin = (
        ampm_df[ampm_df["_asin"] != ""]
        .groupby("_asin", as_index=False)["qty"].sum()
        .set_index("_asin")["qty"].to_dict()
    )
    ampm_by_sku = (
        ampm_df[ampm_df["_sku"] != ""]
        .groupby("_sku", as_index=False)["qty"].sum()
        .set_index("_sku")["qty"].to_dict()
    )
    ampm_by_model = (
        ampm_df[(ampm_df["_asin"] == "") & (ampm_df["_sku"] == "")]
        .groupby("_model", as_index=False)["qty"].sum()
        .set_index("_model")["qty"].to_dict()
    )

    _asin_col = df_plan.get("asin",  pd.Series([""] * len(df_plan))).astype(str).str.strip().str.upper()
    _sku_col  = df_plan.get("sku",   pd.Series([""] * len(df_plan))).astype(str).str.strip().str.upper()
    _mod_col  = df_plan["model"].astype(str).str.strip().str.lower()

    df_plan["ampm_inventory"] = pd.to_numeric(
        pd.Series([
            ampm_by_asin.get(a, ampm_by_sku.get(s, ampm_by_model.get(m, 0)))
            for a, s, m in zip(_asin_col, _sku_col, _mod_col)
        ], index=df_plan.index),
        errors="coerce",
    ).fillna(0)

    # =========================
    # B2B INVENTORY (display only — no calc logic)
    # Same ASIN→SKU→Model cascade as AMPM, filtered to Channel == "B2B - AMPM".
    # =========================
    b2b_raw = get(ampm_file.replace("data/input/", ""))
    b2b_raw = b2b_raw.copy()
    b2b_raw.columns = b2b_raw.columns.str.lower().str.strip()
    b2b_df = b2b_raw[b2b_raw["channel"].str.lower() == "b2b - ampm"].copy()
    b2b_df["_asin"]  = b2b_df.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    b2b_df["_sku"]   = b2b_df.get("sku",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    b2b_df["_model"] = b2b_df["model"].astype(str).str.strip().str.lower()

    b2b_by_asin = (
        b2b_df[b2b_df["_asin"] != ""]
        .groupby("_asin", as_index=False)["qty"].sum()
        .set_index("_asin")["qty"].to_dict()
    )
    b2b_by_sku = (
        b2b_df[b2b_df["_sku"] != ""]
        .groupby("_sku", as_index=False)["qty"].sum()
        .set_index("_sku")["qty"].to_dict()
    )
    b2b_by_model = (
        b2b_df[(b2b_df["_asin"] == "") & (b2b_df["_sku"] == "")]
        .groupby("_model", as_index=False)["qty"].sum()
        .set_index("_model")["qty"].to_dict()
    )

    df_plan["b2b_inventory"] = pd.to_numeric(
        pd.Series([
            b2b_by_asin.get(a, b2b_by_sku.get(s, b2b_by_model.get(m, 0)))
            for a, s, m in zip(_asin_col, _sku_col, _mod_col)
        ], index=df_plan.index),
        errors="coerce",
    ).fillna(0)

    if "category" in df_plan.columns:
        df_plan["category"] = df_plan["category"].fillna("-").astype(str).str.strip().replace("nan", "-")
    else:
        df_plan["category"] = "-"

    if "listing_status" not in df_plan.columns:
        df_plan["listing_status"] = "-"

    # ==========================================================
    # INBOUND-TO-FC (display only — sourced from SP-API pull)
    # Per (SKU, FC) sum of currently-in-flight units (Shipped not yet
    # Received). Reads data/input/inbound_shipments_<account>.csv if it
    # exists; silently defaults to 0 when the file isn't present for
    # an account (so non-Nexlev accounts don't break until each has its
    # own SP-API refresh token wired).
    # ==========================================================
    _acct_slug = {
        "nexlev":         "nexlev",
        "viomi":          "viomi",
        "audio array":    "audio_array",
        "white mulberry": "wm",
        "fossil":         "fossil",
    }.get(account.lower(), account.lower().replace(" ", "_"))

    inbound_csv = Path("data/input") / f"inbound_shipments_{_acct_slug}.csv"
    df_plan["inbound_to_fc"] = 0
    if inbound_csv.exists():
        try:
            inb = pd.read_csv(inbound_csv)
            inb["SellerSKU"]     = inb["SellerSKU"].astype(str).str.strip().str.upper()
            inb["DestinationFC"] = inb["DestinationFC"].astype(str).str.strip().str.upper()
            # Exclude RECEIVING — those units are physically at the FC and will
            # land in FC SOH soon. Counting them as inbound would double-deduct.
            inb["_status"] = inb["ShipmentStatus"].astype(str).str.strip().str.upper()
            inb = inb[inb["_status"] != "RECEIVING"]
            inb["_remaining"]    = (
                pd.to_numeric(inb["QuantityShipped"],  errors="coerce").fillna(0)
              - pd.to_numeric(inb["QuantityReceived"], errors="coerce").fillna(0)
            ).clip(lower=0)
            inb_agg = (
                inb.groupby(["SellerSKU", "DestinationFC"], as_index=False)["_remaining"]
                   .sum()
                   .rename(columns={"_remaining": "inbound_to_fc",
                                    "SellerSKU": "sku",
                                    "DestinationFC": "fulfillment_center"})
            )
            df_plan["sku"]                = df_plan["sku"].astype(str).str.strip().str.upper()
            df_plan["fulfillment_center"] = df_plan["fulfillment_center"].astype(str).str.strip().str.upper()
            df_plan = df_plan.drop(columns=["inbound_to_fc"], errors="ignore")
            df_plan = df_plan.merge(inb_agg, on=["sku", "fulfillment_center"], how="left")
            df_plan["inbound_to_fc"] = pd.to_numeric(
                df_plan["inbound_to_fc"], errors="coerce"
            ).fillna(0).astype(int)

            # Shadow rows — inbound (SKU, FC) pairs that don't exist in the
            # plan (SKU has zero 90-day velocity at that FC, so fc_planning
            # emitted no row). Without this, the 90 IN_TRANSIT units are
            # silently dropped and the operator can't see the incoming
            # shipment on the FC page (e.g. MR-01 → ISK3, 90 units).
            existing = set(zip(df_plan["sku"], df_plan["fulfillment_center"]))
            missing = inb_agg[~inb_agg.apply(
                lambda r: (r["sku"], r["fulfillment_center"]) in existing, axis=1
            )]
            if len(missing):
                # Take the SKU's meta fields (model / asin / category /
                # ampm / b2b / master_carton) from any existing plan row
                # of the same SKU. If the SKU has no plan rows at all,
                # fall back to the master (rare — SKU not in this
                # account's replenishment plan).
                sku_meta_cols = [c for c in [
                    "model", "asin", "category", "listing_status",
                    "ampm_inventory", "b2b_inventory", "hazmat_type",
                    "master_carton",
                ] if c in df_plan.columns]
                sku_meta = (
                    df_plan[["sku"] + sku_meta_cols]
                    .drop_duplicates(subset=["sku"], keep="first")
                )
                shadow = missing.merge(sku_meta, on="sku", how="left")
                # Fill defaults for planning fields — no velocity, no ask,
                # just an inbound landing.
                for c, default in [
                    ("weekly_velocity", 0.0),
                    ("total_units_sold", 0),
                    ("fc_inventory", 0),
                    ("fc_in_transit", 0),
                    ("transfer_in", 0),
                    ("target_cover_units", 0),
                    ("post_transfer_stock", 0),
                    ("coverage_gap_units", 0),
                    ("send_qty", 0),
                    ("expected_units", 0),
                    ("fill_pct", 0),
                    ("velocity_flag", ""),
                    ("ixd_flag", ""),
                    ("allocation_logic", "inbound-only"),
                ]:
                    shadow[c] = default
                # Only keep columns that exist in df_plan so concat aligns
                shadow = shadow[[c for c in df_plan.columns if c in shadow.columns]]
                df_plan = pd.concat([df_plan, shadow], ignore_index=True)
                df_plan["inbound_to_fc"] = pd.to_numeric(
                    df_plan["inbound_to_fc"], errors="coerce"
                ).fillna(0).astype(int)
        except Exception as e:
            print(f"WARN: inbound merge failed for {account}: {e}")
            df_plan["inbound_to_fc"] = 0

    # ==========================================================
    # DEDUCT INBOUND FROM SEND_QTY
    # Units already in flight to a given FC shouldn't be re-shipped from
    # the mother warehouse. For non-Fossil accounts we use the SP-API
    # inbound_to_fc value; Fossil already deducts its own in_transit_qty
    # + open_po_qty above, so we skip it there to avoid double-counting.
    # ==========================================================
    if account.lower() != "fossil" and "inbound_to_fc" in df_plan.columns:
        df_plan["send_qty"] = (
            pd.to_numeric(df_plan["send_qty"], errors="coerce").fillna(0)
            - df_plan["inbound_to_fc"]
        ).clip(lower=0)
        # Round to nearest int — send_qty is always whole units
        df_plan["send_qty"] = df_plan["send_qty"].round(0).astype(int)

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
        "b2b_inventory",
        "inbound_to_fc",
        "fulfillment_center",
        "weekly_velocity",
        "total_units_sold",
        "fc_inventory",
        "fc_in_transit",
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