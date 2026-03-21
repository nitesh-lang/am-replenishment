import pandas as pd
from pathlib import Path
from app.services.file_cache import get, get_excel_sheet

DATA_PATH = Path("data/input")

def load_wm_replenishment(from_week=None, to_week=None, cover_weeks: int = 8):

    try:

        # =========================
        # LOAD FILES
        # =========================

        master_df = get_excel_sheet("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "WM")
        sales_df = get("weekly_sales_snapshot.csv")
        inv_df = get("Inventory_snapshot_WM.xlsx")
        po_df = get("In_Transit_PO data - WM.xlsx")

        # =========================
        # NORMALIZE COLUMNS
        # =========================

        master_df.columns = master_df.columns.str.lower().str.strip()
        sales_df.columns = sales_df.columns.str.lower().str.strip()
        inv_df.columns = inv_df.columns.str.lower().str.strip()
        po_df.columns = po_df.columns.str.lower().str.strip()

        # =========================
        # NORMALIZE VALUES
        # =========================

        master_df["model"] = master_df["model"].astype(str).str.strip()
        sales_df["model"] = sales_df["model"].astype(str).str.strip()
        inv_df["model"] = inv_df["model"].astype(str).str.strip()
        po_df["model"] = po_df["model"].fillna(po_df["sku"]).astype(str).str.strip()

        # =========================
        # BRAND FILTER
        # =========================

        sales_df = sales_df[sales_df["brand"] == "White Mulberry"]

        # =========================
        # SALES WINDOW FILTER
        # =========================

        if "week" in sales_df.columns:
            sales_df["week"] = (
                sales_df["week"].astype(str)
                .str.extract(r"(\d+)")[0]
                .pipe(pd.to_numeric, errors="coerce")
            )
            available_weeks = sorted(
                sales_df["week"].dropna().unique().tolist(),
                reverse=True
            )[:12]

            if from_week in available_weeks and to_week in available_weeks:
                from_idx = available_weeks.index(from_week)
                to_idx = available_weeks.index(to_week)
                selected_weeks = available_weeks[to_idx:from_idx + 1]
            else:
                selected_weeks = available_weeks

            sales_df = sales_df[sales_df["week"].isin(selected_weeks)]
            window_size = max(len(selected_weeks), 1)
        else:
            window_size = 12

        # =========================
        # 1P SALES
        # =========================

        cb_sales = (
            sales_df[sales_df["channel"] == "1p Sales"]
            .groupby("model", as_index=False)["units_sold"]
            .sum()
            .rename(columns={"units_sold": "cb_3m_sales"})
        )

        # =========================
        # AMAZON SALES
        # =========================

        amazon_sales = (
            sales_df[sales_df["channel"] == "Amazon"]
            .groupby("model", as_index=False)["units_sold"]
            .sum()
            .rename(columns={"units_sold": "amazon_3m_sales"})
        )

        # =========================
        # AMPM INVENTORY
        # =========================

        ampm_inventory_df = pd.DataFrame(columns=["model", "ampm_inventory"])

        if "channel" in inv_df.columns:
            print("WM UNIQUE CHANNELS:", inv_df["channel"].str.strip().unique().tolist())

            ampm_raw = inv_df[
                inv_df["channel"].str.strip().str.lower() == "ampm"
            ].groupby("model", as_index=False).sum(numeric_only=True)

            if "qty" in ampm_raw.columns and len(ampm_raw) > 0:
                ampm_inventory_df = ampm_raw.rename(columns={"qty": "ampm_inventory"})[["model", "ampm_inventory"]]

            inv_df = inv_df[inv_df["channel"].str.strip().str.lower() == "1p"]

        inv_df = inv_df.groupby("model", as_index=False).sum(numeric_only=True)

        if "qty" in inv_df.columns:
            inv_df = inv_df.rename(columns={"qty": "final_cb_qty"})

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
        # RENAME MASTER COLUMNS
        # =========================

        master_df = master_df.rename(columns={
            "product type": "hazmat_type",
            "hazmat type": "hazmat_type",
        })

        # =========================
        # MERGE
        # =========================

        df = master_df.merge(cb_sales, on="model", how="left")
        df = df.merge(amazon_sales, on="model", how="left")
        df = df.merge(inv_df[["model", "final_cb_qty"]], on="model", how="left")
        df = df.merge(ampm_inventory_df, on="model", how="left")
        df = df.merge(open_po, on="model", how="left")
        df = df.merge(in_transit, on="model", how="left")

        df = df.fillna(0)

        # =========================
        # CALCULATIONS
        # =========================

        df["total_sales"] = df["cb_3m_sales"] + df["amazon_3m_sales"]
        df["avg_weekly_sales"] = df["total_sales"] / window_size
        df["estimated_qty"] = (df["avg_weekly_sales"] * cover_weeks).round()
        df["deficiency"] = (df["estimated_qty"] - df["final_cb_qty"]).clip(lower=0)
        df["po_requirement"] = (df["deficiency"] - (df["open_po"] + df["in_transit"])).clip(lower=0)

        # =========================
        # DB MERGE
        # =========================

        import psycopg2, os

        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        db_df = pd.read_sql("SELECT * FROM wm_inputs", conn)

        df = df.merge(
            db_df[["model", "po_requirement", "remarks"]],
            on="model",
            how="left",
            suffixes=("", "_db")
        )

        df["po_requirement"] = df["po_requirement_db"].combine_first(df["po_requirement"])
        df["remarks"] = df["remarks"].fillna("")
        df = df.drop(columns=["po_requirement_db"], errors="ignore")

        conn.close()

        return df

    except Exception as e:
        print("WM REPLENISHMENT ERROR:", str(e))
        return pd.DataFrame()