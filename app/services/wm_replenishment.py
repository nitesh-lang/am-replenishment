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

            # AMPM aggregated by lowercase Model (case-insensitive key)
            ampm_filter = inv_df[inv_df["channel"].str.strip().str.lower() == "ampm"].copy()
            ampm_filter["_key"] = ampm_filter["model"].astype(str).str.strip().str.lower()
            ampm_raw = ampm_filter.groupby("_key", as_index=False).sum(numeric_only=True)

            if "qty" in ampm_raw.columns and len(ampm_raw) > 0:
                ampm_inventory_df = ampm_raw.rename(columns={"qty": "ampm_inventory"})[["_key", "ampm_inventory"]]

            inv_df = inv_df[inv_df["channel"].str.strip().str.lower() == "1p"]

        inv_df = inv_df.groupby("model", as_index=False).sum(numeric_only=True)

        if "qty" in inv_df.columns:
            inv_df = inv_df.rename(columns={"qty": "final_cb_qty"})

        # =========================
        # OPEN PO / IN TRANSIT
        # =========================
        # Case-insensitive Delivery Status — source file inconsistently uses
        # "Open po" / "In-Transit" casing (see cb_replenishment.py for context).
        po_df["_status"] = po_df["delivery status"].astype(str).str.strip().str.lower()

        open_po = (
            po_df[po_df["_status"] == "open po"]
            .groupby("model", as_index=False)["accepted quantity"]
            .sum()
            .rename(columns={"accepted quantity": "open_po"})
        )

        in_transit = (
            po_df[po_df["_status"] == "in-transit"]
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
        # Case-insensitive AMPM merge: build a lowercase key on df, drop after merge
        df["_key"] = df["model"].astype(str).str.strip().str.lower()
        df = df.merge(ampm_inventory_df, on="_key", how="left")
        df = df.drop(columns=["_key"])
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

        # Cap PO requirement at AMPM (mother warehouse) stock — can't ship more
        # than what AMPM physically has. Applied BEFORE the DB merge so any
        # user-saved override in wm_inputs still wins below.
        df["po_requirement"] = df[["po_requirement", "ampm_inventory"]].min(axis=1)

        # =========================
        # DB MERGE (remarks only)
        # =========================

        from app.services.db import get_conn

        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS wm_inputs (
                        model TEXT PRIMARY KEY,
                        po_requirement INTEGER DEFAULT 0,
                        remarks TEXT DEFAULT ''
                    )
                """)
                cursor.execute("ALTER TABLE wm_inputs ADD COLUMN IF NOT EXISTS po_requirement INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE wm_inputs ADD COLUMN IF NOT EXISTS remarks TEXT DEFAULT ''")
            conn.commit()

            # Load po_requirement and remarks — DB value wins if user saved it
            db_df = pd.read_sql("SELECT model, po_requirement, remarks FROM wm_inputs", conn)

        if not db_df.empty and "model" in db_df.columns:
            df = df.merge(
                db_df[["model", "po_requirement", "remarks"]],
                on="model",
                how="left",
                suffixes=("", "_db")
            )
            if "po_requirement_db" in df.columns:
                df["po_requirement"] = df["po_requirement_db"].combine_first(df["po_requirement"])
                df = df.drop(columns=["po_requirement_db"], errors="ignore")
            if "remarks_db" in df.columns:
                df["remarks"] = df.get("remarks_db", pd.Series("", index=df.index)).fillna("")
                df = df.drop(columns=["remarks_db"], errors="ignore")

        # Always ensure these columns exist (e.g. after reset when DB is empty)
        if "remarks" not in df.columns:
            df["remarks"] = ""
        if "po_requirement" not in df.columns:
            df["po_requirement"] = 0

        conn.close()

        return df

    except Exception as e:
        print("WM REPLENISHMENT ERROR:", str(e))
        return pd.DataFrame()