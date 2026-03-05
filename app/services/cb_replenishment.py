import pandas as pd
from pathlib import Path

DATA_PATH = Path("data/input")

def load_cb_replenishment():

    master_df = pd.read_excel(DATA_PATH / "CB Replenishment_Master.xlsx")
    sales_df = pd.read_csv(DATA_PATH / "weekly_sales_snapshot - CB Replenishment.csv")

    inv_audio_df = pd.read_excel(DATA_PATH / "Inventory_snapshot_audio_array.xlsx")
    inv_tonor_df = pd.read_excel(DATA_PATH / "Inventory_snapshot_tonor.xlsx")

    inventory_df = pd.concat([inv_audio_df, inv_tonor_df], ignore_index=True)

    # normalize columns
    master_df.columns = master_df.columns.str.lower().str.strip()
    sales_df.columns = sales_df.columns.str.lower().str.strip()
    inventory_df.columns = inventory_df.columns.str.lower().str.strip()

    # sales filter
    sales_df = sales_df[sales_df["brand"].isin(["Audio Array", "Tonor"])]

    cb_sales = (
        sales_df[sales_df["channel"] == "1p"]
        .groupby(["brand","model"], as_index=False)["units_sold"]
        .sum()
        .rename(columns={"units_sold":"cb_3m_sales"})
    )

    cambium_sales = (
        sales_df[sales_df["channel"] != "1p"]
        .groupby(["brand","model"], as_index=False)["units_sold"]
        .sum()
        .rename(columns={"units_sold":"cambium_3m_sales"})
    )

    # inventory
    if "channel" in inventory_df.columns:
        inventory_df = inventory_df[inventory_df["channel"] == "1p"]

    inventory_df = (
        inventory_df.groupby(["brand","model"], as_index=False)
        .sum(numeric_only=True)
    )

    if "qty" in inventory_df.columns:
        inventory_df = inventory_df.rename(columns={"qty":"final_cb_qty"})

    # merge
    df = master_df.merge(cb_sales, on=["brand","model"], how="left")
    df = df.merge(cambium_sales, on=["brand","model"], how="left")
    df = df.merge(inventory_df, on=["brand","model"], how="left")

    df = df.fillna(0)

    df["total_sales"] = df["cb_3m_sales"] + df["cambium_3m_sales"]
    df["avg_weekly_sales"] = df["total_sales"] / 12

    return df