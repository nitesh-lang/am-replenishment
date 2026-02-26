import os
import pandas as pd


def china_reorder_logic(brand: str = "Nexlev", months: int = 3):

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # ==============================
    # SALES FILE (COMMON)
    # ==============================
    sales_path = os.path.join(
        BASE_DIR, "..", "data", "input",
        "weekly_sales_snapshot - ChinaReorder.csv"
    )

    # ==============================
    # INVENTORY FILE MAP (MATCH EXACT FILE NAMES)
    # ==============================
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
        BASE_DIR, "..", "data", "input",
        inv_file
    )

    if not os.path.exists(inv_path):
        raise FileNotFoundError(f"Inventory file missing: {inv_path}")

    print("READING SALES:", sales_path)
    print("READING INVENTORY:", inv_path)

    # ==============================
    # LOAD FILES
    # ==============================
    sales_df = pd.read_csv(sales_path)
    inv_df = pd.read_excel(inv_path, engine="openpyxl")

    # ==============================
    # CLEAN COLUMN NAMES
    # ==============================
    sales_df.columns = sales_df.columns.str.strip().str.lower()
    inv_df.columns = inv_df.columns.str.strip().str.lower()

    # ==============================
    # BRAND FILTER (SAFE)
    # ==============================
    sales_df["brand"] = sales_df["brand"].astype(str).str.strip().str.lower()
    sales_df = sales_df[sales_df["brand"] == brand_clean]

    # ==============================
    # CLEAN MODEL
    # ==============================
    sales_df["model"] = sales_df["model"].astype(str).str.strip()
    inv_df["model"] = inv_df["model"].astype(str).str.strip()

    # ==============================
    # LAST 12 WEEK SALES
    # ==============================
    sales_df = sales_df.sort_values("week", ascending=False)

    last_12 = sales_df.groupby("model").head(12)

    sales_agg = (
        last_12
        .groupby("model", as_index=False)
        .agg(last_12w_sales=("units_sold", "sum"))
    )

    sales_agg["avg_weekly_sales"] = sales_agg["last_12w_sales"] / 12

    # ==============================
    # INVENTORY AGGREGATION
    # ==============================
    inv_agg = (
        inv_df
        .groupby("model", as_index=False)
        .agg(current_inventory=("qty", "sum"))
    )

    # ==============================
    # MERGE
    # ==============================
    df = pd.merge(
        sales_agg,
        inv_agg,
        on="model",
        how="outer"
    ).fillna(0)

    # ==============================
    # CALCULATIONS
    # ==============================
    target_weeks = months * 4  # 1–6 months → 4–24 weeks

    df["avg_weekly_sales"] = pd.to_numeric(df["avg_weekly_sales"], errors="coerce").fillna(0)
    df["current_inventory"] = pd.to_numeric(df["current_inventory"], errors="coerce").fillna(0)

    df["weeks_cover"] = df.apply(
        lambda row: row["current_inventory"] / row["avg_weekly_sales"]
        if row["avg_weekly_sales"] > 0 else 0,
        axis=1
    )

    df["target_stock"] = df["avg_weekly_sales"] * target_weeks

    df["suggested_reorder"] = (
        df["target_stock"] - df["current_inventory"]
    ).clip(lower=0)

    df["remarks"] = ""

    return df.to_dict(orient="records")