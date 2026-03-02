import os
import pandas as pd


def get_china_reorder_working_data(
    brand: str = None,
    channel: str = None,
    model: str = None,
):

    # ============================================================
    # BASE DIRECTORY
    # ============================================================

    BASE_DIR = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )

    # ============================================================
    # FILE PATHS
    # ============================================================

    sales_path = os.path.join(
        BASE_DIR,
        "..",
        "data",
        "input",
        "weekly_sales_snapshot - ChinaReorder.csv"
    )

    inv_path = os.path.join(
        BASE_DIR,
        "..",
        "data",
        "input",
        "inventory_model_snapshot_China Reorder.csv"
    )

    print("READING SALES:", sales_path)
    print("READING INVENTORY:", inv_path)

    # ============================================================
    # LOAD DATA
    # ============================================================

    sales_df = pd.read_csv(sales_path)
    inv_df = pd.read_csv(inv_path)

    # ============================================================
    # CLEAN COLUMN NAMES
    # ============================================================

    sales_df.columns = sales_df.columns.str.strip().str.lower()
    inv_df.columns = inv_df.columns.str.strip().str.lower()

    # ============================================================
    # OPTIONAL FILTERS
    # ============================================================

    if brand:
        sales_df = sales_df[
            sales_df["brand"].str.lower() == brand.lower()
        ]

    if channel:
        sales_df = sales_df[
            sales_df["channel"].str.lower() == channel.lower()
        ]

    if model:
        sales_df = sales_df[
            sales_df["model"].str.lower() == model.lower()
        ]

    # ============================================================
    # AGGREGATE SALES FIRST (avoid weekly duplication)
    # ============================================================

    sales_agg = (
        sales_df
        .groupby(["brand", "model"], as_index=False)
        .agg({
            "units_sold": "sum",
            "gross_sales": "sum",
            "nlc": "sum",
        })
    )

    # ============================================================
    # AGGREGATE INVENTORY FIRST (avoid duplication)
    # ============================================================

    inv_agg = (
        inv_df
        .groupby(["brand", "model"], as_index=False)
        .agg({
            "inventory_units": "sum"
        })
    )

    # ============================================================
    # MERGE AFTER AGGREGATION (safe merge)
    # ============================================================

    final_df = pd.merge(
        sales_agg,
        inv_agg,
        on=["brand", "model"],
        how="left"
    )

    # Replace NaN
    final_df = final_df.fillna(0)

    # ============================================================
    # RETURN FINAL CLEAN DATA
    # ============================================================

    return final_df.to_dict(orient="records")