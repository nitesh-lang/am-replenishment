import os
import pandas as pd


def get_china_reorder_working_data(
    brand: str = None,
    channel: str = None,
    model: str = None,
):

    # ============================================================
    # BASE DIRECTORY (SAME AS WORKING FILE)
    # ============================================================

    BASE_DIR = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )

    # ============================================================
    # SALES FILE
    # ============================================================

    sales_path = os.path.join(
        BASE_DIR,
        "..",
        "data",
        "input",
        "weekly_sales_snapshot - ChinaReorder.csv"
    )

    # ============================================================
    # INVENTORY FILE
    # ============================================================

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
    # LOAD FILES
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
    # MERGE SALES + INVENTORY
    # ============================================================

    df = pd.merge(
        sales_df,
        inv_df,
        on=["brand", "model"],
        how="left"
    )

    return df.to_dict(orient="records")