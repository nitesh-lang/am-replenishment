import pandas as pd
from app.services.file_cache import get


def get_china_reorder_working_data(
    brand: str = None,
    channel: str = None,
    model: str = None,
):

    # ============================================================
    # LOAD DATA
    # ============================================================

    sales_df = get("weekly_sales_snapshot - ChinaReorder.csv")

    # ============================================================
    # CLEAN COLUMN NAMES
    # ============================================================

    sales_df.columns = sales_df.columns.str.strip().str.lower()

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
    # AGGREGATE SALES (avoid weekly duplication)
    # ============================================================

    sales_agg = (
        sales_df
        .groupby(["brand", "model"], as_index=False)
        .agg({
            "units_sold":  "sum",
            "gross_sales": "sum",
            "nlc":         "sum",
        })
    )

    sales_agg = sales_agg.fillna(0)

    # ============================================================
    # RETURN FINAL CLEAN DATA
    # ============================================================

    return sales_agg.to_dict(orient="records")
