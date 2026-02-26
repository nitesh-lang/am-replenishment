print("########## NEW FC FINAL VERSION LOADED ##########")
print("RUNNING FILE:", __file__)

import pandas as pd
from app.services.fc_planning import calculate_fc_plan
from app.services.fc_transfer import calculate_fc_transfers


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
    else:
        repl_path = "data/input/replenishment_master_viomi.xlsx"
        sheet_to_load = "Viomi"

    try:
        repl_master = pd.read_excel(
            repl_path,
            sheet_name=sheet_to_load
        )

        repl_master.columns = repl_master.columns.str.strip()

        repl_master = repl_master.rename(columns={
            "SKU": "sku",
            "Hazmat/non-Hazmat": "ixd_flag",
            "Model": "model"
        })

        repl_master = repl_master[
            ["sku", "model", "ixd_flag"]
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
            columns=["sku", "model", "ixd_flag"]
        )

    df_plan = df_plan.merge(
        repl_master,
        on="sku",
        how="left"
    )

    df_plan["model"] = df_plan["model"].fillna("-")

    IST_PERCENTAGE = 0.35

    def apply_ist(row):
        flag = str(row.get("ixd_flag", "")).strip().lower()

     # If it contains "non-ixd" → NOT governed
        if "non-ixd" in flag:
          return row["send_qty"]

    # Everything else (Hazmat + Non-Hazmat) → governed
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

    # ==========================================================
    # FINAL DATASET
    # ==========================================================

    final_df = pd.DataFrame({
    "Load": df_plan.get("load_flag", ""),
    "Model": df_plan["model"],
    "SKU": df_plan["sku"],
    "FC": df_plan["fulfillment_center"],
    "Send Qty": df_plan["send_qty"],
    "Avg Weekly Sales": df_plan["weekly_velocity"],
    "Ledger Stock": df_plan["fc_inventory"],
    "Target Cover Units": df_plan["target_cover_units"],
    "Original Required": df_plan["original_required_units"],
    "Fill %": df_plan["fill_pct"],
    "Velocity Flag": df_plan["velocity_flag"],
})

    numeric_cleanup_cols = [
        "Send Qty",
    "Avg Weekly Sales",
    "Ledger Stock",
    "Target Cover Units",
    "Original Required",
    "Fill %",
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

    return final_df