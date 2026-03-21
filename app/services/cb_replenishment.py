import pandas as pd
from pathlib import Path

DATA_PATH = Path("data/input")

def load_cb_replenishment(from_week: int = 1, to_week: int = 11, cover_weeks: int = 8):
    """
    from_week   : start of sales window (inclusive), default 1
    to_week     : end   of sales window (inclusive), default 11
    cover_weeks : weeks of cover for estimated_qty,  default 8
    """

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
        # SALES WINDOW FILTER
        # Apply from_week / to_week if the CSV has a "week" column.
        # If the column doesn't exist we fall back to using all rows
        # (same behaviour as before this change).
        # =========================

        if "week" in sales_df.columns:
            sales_df = sales_df[
                sales_df["week"].between(from_week, to_week)
            ]

        window_size = to_week - from_week + 1  # e.g. 1→11 = 11 weeks

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
        ampm_inventory_df = pd.DataFrame(columns=["brand", "model", "ampm_inventory"])

        if "channel" in inventory_df.columns:
            print("UNIQUE CHANNELS IN INVENTORY:", inventory_df["channel"].str.strip().unique().tolist())

            ampm_raw = inventory_df[
                inventory_df["channel"].str.strip().str.lower() == "ampm"
            ].groupby(["brand", "model"], as_index=False).sum(numeric_only=True)

            print("AMPM ROWS FOUND:", len(ampm_raw))

            if "qty" in ampm_raw.columns and len(ampm_raw) > 0:
                ampm_inventory_df = ampm_raw.rename(columns={"qty": "ampm_inventory"})[["brand", "model", "ampm_inventory"]]

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

        master_df = master_df.rename(columns={
            "hazmat type": "hazmat_type",
            "china in transit": "china_in_transit"
        })

        df = master_df.merge(cb_sales, on=["brand","model"], how="left")

        df = df.merge(cambium_sales, on=["brand","model"], how="left")

        df = df.merge(inventory_df, on=["brand","model"], how="left")
        df = df.merge(ampm_inventory_df[["brand", "model", "ampm_inventory"]], on=["brand","model"], how="left")

        df = df.merge(open_po, on="model", how="left")

        df = df.merge(in_transit, on="model", how="left")

        df = df.fillna(0)
        df["remarks"] = ""

        # =========================
        # CALCULATIONS
        # Uses window_size (from_week → to_week) for avg weekly sales
        # Uses cover_weeks for estimated_qty
        # =========================

        df["total_sales"] = df["cb_3m_sales"] + df["cambium_3m_sales"]

        df["avg_weekly_sales"] = df["total_sales"] / window_size

        df["estimated_qty"] = (df["avg_weekly_sales"] * cover_weeks).round()

        df["deficiency"] = df["estimated_qty"] - df["final_cb_qty"]

        df.loc[df["deficiency"] < 0, "deficiency"] = 0

        df["po_requirement"] = (
            df["deficiency"] - (df["open_po"] + df["in_transit"])
        )

        df.loc[df["po_requirement"] < 0, "po_requirement"] = 0

        # =========================
        # DB MERGE (PERSISTED INPUTS)
        # =========================

        import psycopg2, os

        conn = psycopg2.connect(os.environ["DATABASE_URL"])

        db_df = pd.read_sql("SELECT * FROM cb_inputs", conn)

        df = df.merge(
            db_df[["model", "po_requirement", "remarks"]],
            on="model",
            how="left",
            suffixes=("", "_db")
        )

        df["po_requirement"] = df["po_requirement_db"].combine_first(df["po_requirement"])
        df["remarks"] = df["remarks_db"].fillna("")
        df = df.drop(columns=["remarks_db"], errors="ignore")
        df = df.drop(columns=["po_requirement_db"], errors="ignore")

        conn.close()

        return df

    except Exception as e:

        print("CB REPLENISHMENT ERROR:", str(e))

        return pd.DataFrame()
