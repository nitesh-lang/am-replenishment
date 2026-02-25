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

    """
    Final FC Allocation Engine

    1. Pull FC planning
    2. Pull internal FC transfers
    3. Adjust shortfall
    4. Compute final AMPM send quantity
    5. Apply Hazmat governance rule (35%)
    6. Apply velocity delta flag (30% threshold)
    """

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
        df_plan[col] = pd.to_numeric(df_plan[col], errors="coerce").fillna(0)

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
        df_plan["weekly_velocity"] * replenish_weeks
    )

    df_plan["post_transfer_stock"] = (
        df_plan["fc_inventory"] + df_plan["transfer_in"]
    )

    # ==========================================================
    # STEP 4 — ADJUST SHORTFALL
    # ==========================================================

    df_plan["adjusted_shortfall"] = (
        df_plan["target_cover_units"] - df_plan["post_transfer_stock"]
    ).clip(lower=0)

    print("SHORTFALL SAMPLE:")
    print(df_plan[["sku","target_cover_units","post_transfer_stock","adjusted_shortfall"]].head())

    # ==========================================================
    # STEP 5 — FINAL SEND QUANTITY
    # ==========================================================

    df_plan["send_qty"] = df_plan["adjusted_shortfall"]

       # ==========================================================
    # STEP 5B — HAZMAT GOVERNANCE (35%)
    # ==========================================================

    if account.lower() == "nexlev":
        repl_path = "data/input/replenishment_master_nexlev.xlsx"
        sheet_to_load = "Nexlev"
    else:
        repl_path = "data/input/replenishment_master_viomi.xlsx"
        sheet_to_load = "Viomi"

    repl_master = pd.read_excel(repl_path, sheet_name=sheet_to_load)
    repl_master.columns = repl_master.columns.str.strip()

    repl_master = repl_master.rename(columns={
        "SKU": "sku",
        "Hazmat/non-Hazmat": "ixd_flag",
        "Model": "model"
    })

    repl_master = repl_master[["sku", "model", "ixd_flag"]]

    df_plan["sku"] = df_plan["sku"].astype(str).str.strip().str.upper()
    repl_master["sku"] = repl_master["sku"].astype(str).str.strip().str.upper()

    df_plan = df_plan.merge(repl_master, on="sku", how="left")
    print("MODEL DEBUG SAMPLE:")
    print(df_plan[["sku", "model"]].head(10))
    df_plan["model"] = df_plan["model"].fillna("-")

    IST_PERCENTAGE = 0.35

    def apply_ist(row):
        flag = str(row.get("ixd_flag", "")).strip().lower()
        if flag == "non-ixd non hazmat":
            return row["send_qty"]
        return row["send_qty"] * IST_PERCENTAGE

    df_plan["send_qty"] = df_plan.apply(apply_ist, axis=1)


    # ==========================================================
    # STEP 5C — VELOCITY DELTA FLAGGING (30% RULE)
    # ==========================================================

    df_plan["expected_units"] = (
        df_plan["weekly_velocity"] * replenish_weeks
    )

    print("EXPECTED UNITS SAMPLE:")
    print(df_plan[["sku","weekly_velocity","expected_units"]].head())


    df_plan["velocity_fill_ratio"] = (
    df_plan["send_qty"] /
    df_plan["expected_units"].replace(0, 1)
)

    df_plan["velocity_flag"] = df_plan["velocity_fill_ratio"].apply(
        lambda x: "SHORTFALL_30%+" if x < 0.70 else "OK"
    )

    # ==========================================================
    # STEP 6 — EXPLAINABILITY COLUMNS
    # ==========================================================

    df_plan["allocation_logic"] = (
        "send_qty = max(0, weekly_velocity * replenish_weeks "
        "- (fc_inventory + transfer_in))"
    )

    df_plan["coverage_gap_units"] = df_plan["adjusted_shortfall"]

    # ==========================================================
    # FINAL DATASET FOR UI
    # ==========================================================

    final_df = df_plan[[
        "model",   # ✅ add this
        "sku",
        "fulfillment_center",
        "weekly_velocity",
        "fc_inventory",
        "transfer_in",
        "target_cover_units",
        "post_transfer_stock",
        "coverage_gap_units",
        "send_qty",
        "expected_units",
        "velocity_fill_ratio",
        "velocity_flag",
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
        "velocity_fill_ratio"
    ]

    for col in numeric_cleanup_cols:
        final_df[col] = pd.to_numeric(
            final_df[col],
            errors="coerce"
        ).fillna(0)
    
    print("FINAL DF COLUMNS:", final_df.columns.tolist())
    print(final_df[["sku", "model"]].head())

    return final_df