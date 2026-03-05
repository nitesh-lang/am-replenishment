import pandas as pd
from pathlib import Path

DATA_PATH = Path("data/input")

def load_cb_replenishment():

    # -----------------------------
    # LOAD FILES
    # -----------------------------
    master_df = pd.read_excel(DATA_PATH / "CB Replenishment_Master.xlsx")
    sales_df = pd.read_csv(DATA_PATH / "weekly_sales_snapshot - CB Replenishment.csv")

    inv_audio_df = pd.read_excel(DATA_PATH / "Inventory_snapshot_audio_array.xlsx")
    inv_tonor_df = pd.read_excel(DATA_PATH / "Inventory_snapshot_tonor.xlsx")

    inventory_df = pd.concat([inv_audio_df, inv_tonor_df], ignore_index=True)

    # -----------------------------
    # NORMALIZE COLUMN NAMES
    # -----------------------------
    master_df.columns = master_df.columns.str.lower().str.strip()
    sales_df.columns = sales_df.columns.str.lower().str.strip()
    inventory_df.columns = inventory_df.columns.str.lower().str.strip()

    # -----------------------------
    # NORMALIZE BRAND / MODEL
    # -----------------------------
    master_df["brand"] = master_df["brand"].astype(str).str.strip()
    sales_df["brand"] = sales_df["brand"].astype(str).str.strip()
    inventory_df["brand"] = inventory_df["brand"].astype(str).str.strip()

    master_df["model"] = master_df["model"].astype(str).str.strip().str.upper()
    sales_df["model"] = sales_df["model"].astype(str).str.strip().str.upper()
    inventory_df["model"] = inventory_df["model"].astype(str).str.strip().str.upper()

    # -----------------------------
    # FILTER BRANDS
    # -----------------------------
    sales_df = sales_df[sales_df["brand"].isin(["Audio Array", "Tonor"])]

    # -----------------------------
    # CB SALES (1P)
    # -----------------------------
    cb_sales = (
        sales_df[sales_df["channel"].str.lower().str.contains("1p", na=False)]
        .groupby(["brand", "model"], as_index=False)["units_sold"]
        .sum()
        .rename(columns={"units_sold": "cb_3m_sales"})
    )

    # -----------------------------
    # CAMBIUM SALES (NON 1P)
    # -----------------------------
    cambium_sales = (
        sales_df[~sales_df["channel"].str.lower().str.contains("1p", na=False)]
        .groupby(["brand", "model"], as_index=False)["units_sold"]
        .sum()
        .rename(columns={"units_sold": "cambium_3m_sales"})
    )

    # -----------------------------
    # INVENTORY (ONLY 1P)
    # -----------------------------
    if "channel" in inventory_df.columns:
        inventory_df = inventory_df[inventory_df["channel"].str.lower() == "1p"]

    inventory_df = (
        inventory_df.groupby(["brand", "model"], as_index=False)
        .sum(numeric_only=True)
    )

    if "qty" in inventory_df.columns:
        inventory_df = inventory_df.rename(columns={"qty": "final_cb_qty"})

    # -----------------------------
    # MERGE DATA
    # -----------------------------
    df = master_df.merge(cb_sales, on=["brand", "model"], how="left")
    df = df.merge(cambium_sales, on=["brand", "model"], how="left")
    df = df.merge(inventory_df[["brand", "model", "final_cb_qty"]], on=["brand", "model"], how="left")

    # -----------------------------
    # CLEAN NA
    # -----------------------------
    df["cb_3m_sales"] = df["cb_3m_sales"].fillna(0)
    df["cambium_3m_sales"] = df["cambium_3m_sales"].fillna(0)
    df["final_cb_qty"] = df["final_cb_qty"].fillna(0)

    # -----------------------------
    # CALCULATIONS
    # -----------------------------
    df["total_sales"] = df["cb_3m_sales"] + df["cambium_3m_sales"]

    # weekly velocity (3 months ≈ 12 weeks)
    df["avg_weekly_sales"] = df["total_sales"] / 12

    return df