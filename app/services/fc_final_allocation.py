print("########## NEW FC FINAL VERSION LOADED ##########")
print("RUNNING FILE:", __file__)

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


    print("🔥 FC FINAL LIVE CHECK 🔥")
    print("🚀 VELOCITY FLAG VERSION ACTIVE 🚀")

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
    print("FINAL ALLOCATION ACCOUNT:", account)
    print("PLAN ROWS:", len(df_plan))
    print("PLAN TOTAL REQUIRED:", df_plan["required_units"].sum())
    # ==========================================================
    # STEP 2 — LOAD TRANSFER DATA
    # ==========================================================

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
    

    print(
    df_plan[[
        "sku",
        "target_cover_units",
        "post_transfer_stock",
        "adjusted_shortfall"
    ]].head(20)
)
    
    # NOW create expected_units
    df_plan["expected_units"] = df_plan["original_required_units"]

    # ==========================================================
    # STEP 5B — HAZMAT GOVERNANCE (35%)
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
        print("📋 MASTER SHEET COLUMNS:", repl_master.columns.tolist())

        if account.lower() in ["nexlev", "viomi"]:
            repl_master = repl_master.rename(columns={
                "SKU": "sku",
                "Hazmat/non-Hazmat": "ixd_flag",
                "Hazmat Type": "hazmat_type",
                "Model": "model",
                "Category": "category",
                "ASIN": "asin",
                "Master Carton": "master_carton"
            })
        else:
            repl_master = repl_master.rename(columns={
                "SKU": "sku",
                "Product Type": "ixd_flag",
                "Model": "model",
                "Category": "category",
                "ASIN": "asin",
                "Master Carton": "master_carton"
            })
            repl_master["hazmat_type"] = repl_master["ixd_flag"]

        repl_master["category"] = repl_master.get("category", pd.Series(dtype=str)).fillna("-")

        repl_master = repl_master[
            ["sku", "model", "ixd_flag", "hazmat_type", "category", "asin", "master_carton"]
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
            columns=["sku", "model", "ixd_flag", "hazmat_type", "category", "asin", "master_carton"]
        )

        print("📋 MASTER SHEET COLUMNS:", repl_master.columns.tolist())

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
    # ==========================================================
    # FINAL DATASET
    # ==========================================================

    final_df = df_plan[[
        "model",
        "sku",
        "asin",
        "category",
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

    print("FINAL DF COLUMNS:", final_df.columns.tolist())
    print("COLUMNS INSIDE SERVICE:", final_df.columns.tolist())
    print("COLUMNS BEING RETURNED:", final_df.columns.tolist())
    print("SAMPLE ROW RETURNED:", final_df.head(1).to_dict(orient="records"))
    
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
    
    final_df[numeric_cleanup_cols] = (
    final_df[numeric_cleanup_cols]
    .round(0)
    .astype(int)
)

    return final_df