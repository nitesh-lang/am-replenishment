import pandas as pd
from pathlib import Path


DATA_PATH = Path("data/input")


def load_cb_replenishment():

    # -----------------------------
    # Load Files
    # -----------------------------
    master_path = DATA_PATH / "CB Replenishment_Master.xlsx"
    sales_path = DATA_PATH / "weekly_sales_snapshot - CB Replenishment.csv"
    inv_audio_path = DATA_PATH / "Inventory_snapshot_audio_array.xlsx"
    inv_tonor_path = DATA_PATH / "Inventory_snapshot_tonor.xlsx"

    master_df = pd.read_excel(master_path)
    sales_df = pd.read_csv(sales_path)

    inv_audio_df = pd.read_excel(inv_audio_path)
    inv_tonor_df = pd.read_excel(inv_tonor_path)

    inventory_df = pd.concat([inv_audio_df, inv_tonor_df], ignore_index=True)

    # -----------------------------
    # Filter Brands
    # -----------------------------
    sales_df = sales_df[sales_df["brand"].isin(["Audio Array", "Tonor"])]

    # -----------------------------
    # CB Sales (1P)
    # -----------------------------
    cb_sales = (
        sales_df[sales_df["channel"] == "1p"]
        .groupby(["brand", "model"])["units_sold"]
        .sum()
        .reset_index()
        .rename(columns={"units_sold": "cb_3m_sales"})
    )

    # -----------------------------
    # Cambium Sales (Non 1P)
    # -----------------------------
    cambium_sales = (
        sales_df[sales_df["channel"] != "1p"]
        .groupby(["brand", "model"])["units_sold"]
        .sum()
        .reset_index()
        .rename(columns={"units_sold": "cambium_3m_sales"})
    )

    # -----------------------------
    # Inventory (1P only)
    # -----------------------------
    inventory_df = inventory_df[inventory_df["Channel"] == "1p"]

    inventory_df = (
        inventory_df.groupby(["Brand", "Model"])["Qty"]
        .sum()
        .reset_index()
        .rename(columns={
            "Brand": "brand",
            "Model": "model",
            "Qty": "final_cb_qty"
        })
    )

    # -----------------------------
    # Merge Data
    # -----------------------------
    df = master_df.merge(cb_sales, on=["brand", "model"], how="left")
    df = df.merge(cambium_sales, on=["brand", "model"], how="left")
    df = df.merge(inventory_df, on=["brand", "model"], how="left")

    df.fillna(0, inplace=True)

    # -----------------------------
    # Calculations
    # -----------------------------
    df["total_sales"] = df["cb_3m_sales"] + df["cambium_3m_sales"]

    df["avg_weekly_sales"] = df["total_sales"] / 12

    return df