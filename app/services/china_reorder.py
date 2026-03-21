import os
import pandas as pd
from app.services.file_cache import get


def china_reorder_logic(
    brand: str = "Nexlev",
    months: int = 3,
    channel: str = None,
    from_week=None,
    to_week=None,
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

    print("READING SALES (cached): weekly_sales_snapshot - ChinaReorder.csv")
    print("READING INVENTORY (cached):", inv_file)

    # ============================================================
    # LOAD FILES
    # ============================================================

    sales_df = get("weekly_sales_snapshot - ChinaReorder.csv")
    inv_df = get(inv_file)

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
    # SALES WINDOW FILTER
    # ============================================================

    sales_df["week_num"] = (
        sales_df["week"].astype(str)
        .str.extract(r"(\d+)")[0]
        .pipe(pd.to_numeric, errors="coerce")
    )

    available_weeks = sorted(
        sales_df["week_num"].dropna().unique().tolist(),
        reverse=True
    )[:12]

    if from_week in available_weeks and to_week in available_weeks:
        from_idx = available_weeks.index(from_week)
        to_idx = available_weeks.index(to_week)
        selected_weeks = available_weeks[to_idx:from_idx + 1]
    else:
        selected_weeks = available_weeks

    last_12 = sales_df[sales_df["week_num"].isin(selected_weeks)]
    window_size = max(len(selected_weeks), 1)

    # ============================================================
    # SALES AGGREGATION
    # ============================================================

    sales_agg = (
        last_12
        .groupby("model", as_index=False)
        .agg(last_12w_sales=("units_sold", "sum"))
    )

    sales_agg["avg_weekly_sales"] = (
        sales_agg["last_12w_sales"] / window_size
    )

    # ============================================================
    # INVENTORY SPLIT
    # ============================================================
    open_order_df = inv_df[inv_df["channel"] == "open order"]
    pipeline_df   = inv_df[inv_df["channel"] == "pipeline"]
    inventory_df  = inv_df[
        ~inv_df["channel"].isin(["open order", "pipeline"])
    ]

    # ============================================================
    # CATEGORY MAPPING (from inventory)
    # ============================================================

    cat_cols = [c for c in inv_df.columns if c.startswith("category")]
    if cat_cols:
        category_map = (
            inv_df[["model"] + cat_cols]
            .drop_duplicates(subset="model")
        )
    else:
        category_map = pd.DataFrame(columns=["model"])

    # ============================================================
    # CURRENT INVENTORY AGG
    # ============================================================

    inventory_agg = (
        inventory_df
        .groupby("model", as_index=False)
        .agg(current_inventory=("qty", "sum"))
    )

    # ============================================================
    # OPEN ORDER AGG
    # ============================================================

    open_order_agg = (
        open_order_df
        .groupby("model", as_index=False)
        .agg(open_order_qty=("qty", "sum"))
    )

    # ============================================================
    # PIPELINE AGG
    # ============================================================

    pipeline_agg = (
        pipeline_df
        .groupby("model", as_index=False)
        .agg(pipeline_qty=("qty", "sum"))
    )

    # ============================================================
    # MERGE INVENTORY + OPEN ORDER + PIPELINE
    # ============================================================

    inv_agg = pd.merge(inventory_agg, open_order_agg, on="model", how="outer")
    inv_agg = pd.merge(inv_agg, pipeline_agg, on="model", how="outer")
    inv_agg = inv_agg.fillna(0)

    # ============================================================
    # FINAL MERGE (SALES + INVENTORY)
    # ============================================================

    df = pd.merge(sales_agg, inv_agg, on="model", how="outer").fillna(0)

    # Merge category columns
    if not category_map.empty and len(category_map.columns) > 1:
        df = df.merge(category_map, on="model", how="left")
        for col in cat_cols:
            df[col] = df[col].fillna("")

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
        df["target_stock"] - df["current_inventory"] - df["open_order_qty"] - df["pipeline_qty"]
    ).clip(lower=0)

    # ============================================================
    # OPTIONAL REMARKS COLUMN
    # ============================================================

    df["remarks"] = ""

    # ============================================================
    # RETURN JSON
    # ============================================================

    return df.to_dict(orient="records")