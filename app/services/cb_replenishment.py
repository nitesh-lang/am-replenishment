import pandas as pd
from pathlib import Path

DATA_PATH = Path("data/input")

def load_cb_replenishment():

    try:

        # =========================
        # LOAD FILES
        # =========================

        master_df = pd.read_excel(DATA_PATH / "CB Replenishment_Master.xlsx")

        sales_df = pd.read_csv(
            DATA_PATH / "weekly_sales_snapshot - CB Replenishment.csv"
        )

        inv_audio_df = pd.read_excel(
            DATA_PATH / "Inventory_snapshot_audio_array.xlsx"
        )

        inv_tonor_df = pd.read_excel(
            DATA_PATH / "Inventory_snapshot_tonor.xlsx"
        )

        po_df = pd.read_excel(
            DATA_PATH / "In_Transit_PO data.xlsx"
        )

        inventory_df = pd.concat(
            [inv_audio_df, inv_tonor_df],
            ignore_index=True
        )

        # =========================
        # NORMALIZE COLUMNS
        # =========================

        master_df.columns = master_df.columns.str.lower().str.strip()
        sales_df.columns = sales_df.columns.str.lower().str.strip()
        inventory_df.columns = inventory_df.columns.str.lower().str.strip()
        po_df.columns = po_df.columns.str.lower().str.strip()

        # =========================
        # NORMALIZE VALUES
        # =========================

        for df in [master_df, sales_df, inventory_df]:
            df["brand"] = df["brand"].astype(str).str.strip()
            df["model"] = df["model"].astype(str).str.strip()

        po_df["model"] = po_df["model"].fillna(po_df["sku"]).astype(str).str.strip()

        # =========================
        # BRAND FILTER
        # =========================

        sales_df = sales_df[
            sales_df["brand"].isin(["Audio Array", "Tonor"])
        ]

        # =========================
        # CB SALES
        # =========================

        cb_sales = (
            sales_df[sales_df["channel"] == "1p Sales"]
            .groupby(["brand", "model"], as_index=False)["units_sold"]
            .sum()
            .rename(columns={"units_sold": "cb_3m_sales"})
        )

        # =========================
        # CAMBIUM SALES
        # =========================

        cambium_sales = (
            sales_df[sales_df["channel"] == "Amazon"]
            .groupby(["brand", "model"], as_index=False)["units_sold"]
            .sum()
            .rename(columns={"units_sold": "cambium_3m_sales"})
        )

        # =========================
        # INVENTORY
        # =========================

        if "channel" in inventory_df.columns:
            inventory_df = inventory_df[
                inventory_df["channel"].str.lower() == "1p"
            ]

        inventory_df = (
            inventory_df.groupby(["brand", "model"], as_index=False)
            .sum(numeric_only=True)
        )

        if "qty" in inventory_df.columns:
            inventory_df = inventory_df.rename(
                columns={"qty": "final_cb_qty"}
            )

        # =========================
        # OPEN PO / IN TRANSIT
        # =========================

        open_po = (
            po_df[po_df["delivery status"] == "Open PO"]
            .groupby("model", as_index=False)["accepted quantity"]
            .sum()
            .rename(columns={"accepted quantity": "open_po"})
        )

        in_transit = (
            po_df[po_df["delivery status"] == "In-Transit"]
            .groupby("model", as_index=False)["accepted quantity"]
            .sum()
            .rename(columns={"accepted quantity": "in_transit"})
        )

        # =========================
        # MERGE
        # =========================

        df = master_df.merge(cb_sales, on=["brand","model"], how="left")

        df = df.merge(cambium_sales, on=["brand","model"], how="left")

        df = df.merge(inventory_df, on=["brand","model"], how="left")

        df = df.merge(open_po, on="model", how="left")

        df = df.merge(in_transit, on="model", how="left")

        df = df.fillna(0)

        # =========================
        # CALCULATIONS
        # =========================

        df["total_sales"] = df["cb_3m_sales"] + df["cambium_3m_sales"]

        df["avg_weekly_sales"] = df["total_sales"] / 12

        # estimated qty based on 8 weeks coverage
        df["estimated_qty"] = (df["avg_weekly_sales"] * 8).round()

        # deficiency
        df["deficiency"] = df["estimated_qty"] - df["final_cb_qty"]

        df.loc[df["deficiency"] < 0, "deficiency"] = 0

        # PO requirement excluding Open PO + In-Transit
        df["po_requirement"] = (
            df["deficiency"] - (df["open_po"] + df["in_transit"])
        )

        df.loc[df["po_requirement"] < 0, "po_requirement"] = 0

        return df

    except Exception as e:

        print("CB REPLENISHMENT ERROR:", str(e))

        return pd.DataFrame()