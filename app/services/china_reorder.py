import pandas as pd

def china_reorder_logic():

    sales_df = pd.read_csv("data/weekly_sales_snapshot.csv")
    inv_df = pd.read_csv("data/inventory_snapshot.csv")

    # SALES (Last 12 weeks)
    last_12 = (
        sales_df
        .sort_values("Week", ascending=False)
        .groupby("Model")
        .head(12)
    )

    sales = (
        last_12
        .groupby("Model", as_index=False)
        .agg(last_12w_sales=("Qty", "sum"))
    )

    sales["avg_weekly_sales"] = sales["last_12w_sales"] / 12

    # INVENTORY
    inventory = (
        inv_df
        .groupby("Model", as_index=False)
        .agg(current_inventory=("Qty", "sum"))
    )

    df = sales.merge(inventory, on="Model", how="outer").fillna(0)

    TARGET_WEEKS = 12

    df["weeks_cover"] = df["current_inventory"] / df["avg_weekly_sales"].replace(0, 1)
    df["target_stock"] = df["avg_weekly_sales"] * TARGET_WEEKS
    df["suggested_reorder"] = (df["target_stock"] - df["current_inventory"]).clip(lower=0)

    df["remarks"] = ""

    return df.to_dict(orient="records")