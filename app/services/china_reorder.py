import os
import pandas as pd


def china_reorder_logic(
    brand: str = "Nexlev",
    months: int = 3,
    channel: str = None
):

    # ============================================================
    # BASE DIRECTORY
    # ============================================================

    BASE_DIR = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )

    # ============================================================
    # SALES FILE (COMMON)
    # ============================================================

    sales_path = os.path.join(
        BASE_DIR,
        "..",
        "data",
        "input",
        "weekly_sales_snapshot - ChinaReorder.csv"
    )

    # ============================================================
    # INVENTORY FILE MAP
    # ============================================================

    brand_inventory_map = {
        "nexlev": "inventory_snapshot_nexlev.xlsx",
        "audio array": "Inventory_snapshot_audio_array.xlsx",
        "tonor": "Inventory_snapshot_tonor.xlsx",
        "white mulberry": "Inventory_snapshot_WM.xlsx"
    }

    brand_clean = brand.strip().lower()

    if brand_clean not in brand_inventory_map:
        raise ValueError(f"Invalid brand received: {brand}")

    inv_file = brand_inventory_map[brand_clean]

    inv_path = os.path.join(
        BASE_DIR,
        "..",
        "data",
        "input",
        inv_file
    )

    if not os.path.exists(inv_path):
        raise FileNotFoundError(
            f"Inventory file missing: {inv_path}"
        )

    print("READING SALES:", sales_path)
    print("READING INVENTORY:", inv_path)

    # ============================================================
    # LOAD FILES
    # ============================================================

    sales_df = pd.read_csv(sales_path)
    inv_df = pd.read_excel(inv_path, engine="openpyxl")

    # ============================================================
    # CLEAN COLUMN NAMES
    # ============================================================

    sales_df.columns = (
        sales_df.columns
        .str.strip()
        .str.lower()
    )

    inv_df.columns = (
        inv_df.columns
        .str.strip()
        .str.lower()
    )

    # ============================================================
    # CLEAN IMPORTANT FIELDS
    # ============================================================

    sales_df["brand"] = (
        sales_df["brand"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    sales_df["model"] = (
        sales_df["model"]
        .astype(str)
        .str.strip()
    )

    inv_df["model"] = (
        inv_df["model"]
        .astype(str)
        .str.strip()
    )

    inv_df["channel"] = (
        inv_df["channel"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    # ============================================================
    # BRAND FILTER
    # ============================================================

    sales_df = sales_df[
        sales_df["brand"] == brand_clean
    ]

    # ============================================================
    # SALES AGGREGATION (LAST 12 WEEKS)
    # ============================================================

    sales_df = sales_df.sort_values(
        "week",
        ascending=False
    )

    last_12 = (
        sales_df
        .groupby("model")
        .head(12)
    )

    sales_agg = (
        last_12
        .groupby("model", as_index=False)
        .agg(
            last_12w_sales=("units_sold", "sum")
        )
    )

    sales_agg["avg_weekly_sales"] = (
        sales_agg["last_12w_sales"] / 12
    )

    # ============================================================
    # INVENTORY SPLIT
    # ============================================================
    open_order_df = inv_df[
    (inv_df["channel"] == "open order") |
    (inv_df.get("type", "").astype(str).str.lower() == "in-transit inventory")
]

    inventory_df = inv_df.drop(open_order_df.index)

    # ============================================================
    # CURRENT INVENTORY AGG
    # ============================================================

    inventory_agg = (
        inventory_df
        .groupby("model", as_index=False)
        .agg(
            current_inventory=("qty", "sum")
        )
    )

    # ============================================================
    # OPEN ORDER AGG
    # ============================================================

    open_order_agg = (
        open_order_df
        .groupby("model", as_index=False)
        .agg(
            open_order_qty=("qty", "sum")
        )
    )

    # ============================================================
    # MERGE INVENTORY + OPEN ORDER
    # ============================================================

    inv_agg = pd.merge(
        inventory_agg,
        open_order_agg,
        on="model",
        how="outer"
    ).fillna(0)

    # ============================================================
    # FINAL MERGE (SALES + INVENTORY)
    # ============================================================

    df = pd.merge(
        sales_agg,
        inv_agg,
        on="model",
        how="outer"
    ).fillna(0)

    # ============================================================
    # ENSURE NUMERIC TYPES
    # ============================================================

    df["avg_weekly_sales"] = pd.to_numeric(
        df["avg_weekly_sales"],
        errors="coerce"
    ).fillna(0)

    df["current_inventory"] = pd.to_numeric(
        df["current_inventory"],
        errors="coerce"
    ).fillna(0)

    df["open_order_qty"] = pd.to_numeric(
        df["open_order_qty"],
        errors="coerce"
    ).fillna(0)

    # ============================================================
    # CALCULATIONS
    # ============================================================

    target_weeks = months * 4

    df["weeks_cover"] = df.apply(
        lambda row:
        row["current_inventory"] / row["avg_weekly_sales"]
        if row["avg_weekly_sales"] > 0 else 0,
        axis=1
    )

    df["target_stock"] = (
        df["avg_weekly_sales"] * target_weeks
    )

    df["suggested_reorder"] = (
        df["target_stock"] - df["current_inventory"]
    ).clip(lower=0)

    # ============================================================
    # OPTIONAL REMARKS COLUMN
    # ============================================================

    df["remarks"] = ""

    # ============================================================
    # RETURN JSON
    # ============================================================

    return df.to_dict(orient="records")