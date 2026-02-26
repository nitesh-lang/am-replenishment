import os
import pandas as pd

def china_reorder_logic():

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    sales_path = os.path.join(
        BASE_DIR, "..", "data", "input", "weekly_sales_snapshot - ChinaReorder.csv"
    )

    inv_path = os.path.join(
        BASE_DIR, "..", "data", "input", "inventory_snapshot_nexlev.xlsx"
    )

    print("READING FILE:", sales_path)

    sales_df = pd.read_csv(sales_path)
    inv_df = pd.read_excel(inv_path, engine="openpyxl")

    sales_df.columns = sales_df.columns.str.strip().str.lower()
    inv_df.columns = inv_df.columns.str.strip().str.lower()

    # ❌ NO BRAND FILTER HERE

    sales_df["model"] = sales_df["model"].str.strip()
    inv_df["model"] = inv_df["model"].str.strip()

    sales_df = sales_df.sort_values("week", ascending=False)

    last_12 = (
        sales_df
        .groupby("model")
        .head(12)
    )

    sales_agg = (
        last_12
        .groupby("model", as_index=False)
        .agg(last_12w_sales=("units_sold", "sum"))
    )

    sales_agg["avg_weekly_sales"] = sales_agg["last_12w_sales"] / 12

    inv_agg = (
        inv_df
        .groupby("model", as_index=False)
        .agg(current_inventory=("qty", "sum"))
    )

    df = pd.merge(
        sales_agg,
        inv_agg,
        on="model",
        how="outer"
    ).fillna(0)

    TARGET_WEEKS = 12

    df["weeks_cover"] = (
        df["current_inventory"] /
        df["avg_weekly_sales"].replace(0, 1)
    )

    df["target_stock"] = df["avg_weekly_sales"] * TARGET_WEEKS

    df["suggested_reorder"] = (
        df["target_stock"] - df["current_inventory"]
    ).clip(lower=0)

    df["remarks"] = ""

    return df.to_dict(orient="records")