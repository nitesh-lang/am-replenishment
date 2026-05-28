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
        # SALES — ASIN primary, SKU fallback, Model fallback (exclusive)
        # =========================
        # Same cascade standard as CB and replenishment.py — ASIN-keyed
        # attribution avoids the duplicate-Model double-count and remains
        # resilient if WM master ever picks up duplicate Models.
        sales_df["_asin"] = sales_df.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
        sales_df["_sku"]  = sales_df.get("sku",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})

        def _sales_agg(channel: str, level: str, out_name: str) -> pd.DataFrame:
            sub = sales_df[sales_df["channel"] == channel]
            if level == "asin":
                sub = sub[sub["_asin"] != ""]
                return sub.groupby("_asin", as_index=False)["units_sold"].sum().rename(columns={"units_sold": out_name})
            if level == "sku":
                sub = sub[(sub["_asin"] == "") & (sub["_sku"] != "")]
                return sub.groupby("_sku", as_index=False)["units_sold"].sum().rename(columns={"units_sold": out_name})
            sub = sub[(sub["_asin"] == "") & (sub["_sku"] == "")]
            return sub.groupby("model", as_index=False)["units_sold"].sum().rename(columns={"units_sold": out_name})

        cb_sales_by_asin     = _sales_agg("1p Sales", "asin",  "cb_3m_sales_asin")
        cb_sales_by_sku      = _sales_agg("1p Sales", "sku",   "cb_3m_sales_sku")
        cb_sales_by_model    = _sales_agg("1p Sales", "model", "cb_3m_sales_model")
        amazon_sales_by_asin = _sales_agg("Amazon",   "asin",  "amazon_3m_sales_asin")
        amazon_sales_by_sku  = _sales_agg("Amazon",   "sku",   "amazon_3m_sales_sku")
        amazon_sales_by_model= _sales_agg("Amazon",   "model", "amazon_3m_sales_model")

        # =========================
        # AMPM INVENTORY — ASIN primary, SKU fallback
        # =========================
        ampm_by_asin = pd.DataFrame(columns=["_asin", "ampm_inventory_asin"])
        ampm_by_sku  = pd.DataFrame(columns=["_sku",  "ampm_inventory_sku"])

        if "channel" in inv_df.columns:
            print("WM UNIQUE CHANNELS:", inv_df["channel"].str.strip().unique().tolist())

            ampm_raw = inv_df[inv_df["channel"].str.strip().str.lower() == "ampm"].copy()
            if "qty" in ampm_raw.columns and len(ampm_raw) > 0:
                ampm_raw["_asin"] = ampm_raw.get("asin", "").astype(str).str.strip().str.upper()
                ampm_raw["_sku"]  = ampm_raw.get("sku",  "").astype(str).str.strip().str.upper()
                ampm_by_asin = (
                    ampm_raw[ampm_raw["_asin"] != ""].groupby("_asin", as_index=False)["qty"].sum()
                    .rename(columns={"qty": "ampm_inventory_asin"})
                )
                ampm_by_sku = (
                    ampm_raw[ampm_raw["_sku"] != ""].groupby("_sku", as_index=False)["qty"].sum()
                    .rename(columns={"qty": "ampm_inventory_sku"})
                )

            inv_df = inv_df[inv_df["channel"].str.strip().str.lower() == "1p"]

        # 1P inventory aggregated by ASIN (preferred) or model fallback
        inv_df["_asin"] = inv_df.get("asin", "").astype(str).str.strip().str.upper()
        inv_1p_by_asin = (
            inv_df[inv_df["_asin"] != ""].groupby("_asin", as_index=False)["qty"].sum()
            .rename(columns={"qty": "final_cb_qty_asin"}) if "qty" in inv_df.columns else
            pd.DataFrame(columns=["_asin", "final_cb_qty_asin"])
        )
        inv_1p_by_model = (
            inv_df.groupby("model", as_index=False)["qty"].sum()
            .rename(columns={"qty": "final_cb_qty_model"}) if "qty" in inv_df.columns else
            pd.DataFrame(columns=["model", "final_cb_qty_model"])
        )

        # =========================
        # OPEN PO / IN TRANSIT — ASIN primary, SKU fallback
        # =========================
        po_df["_status"] = po_df["delivery status"].astype(str).str.strip().str.lower() if "delivery status" in po_df.columns else ""
        po_df["_asin"]   = po_df.get("asin", "").astype(str).str.strip().str.upper()
        po_df["_sku"]    = po_df.get("sku",  "").astype(str).str.strip().str.upper()

        def _po_agg(status: str, key: str, name: str) -> pd.DataFrame:
            sub = po_df[po_df["_status"] == status]
            if key not in sub.columns or sub.empty:
                return pd.DataFrame(columns=[key, name])
            return (
                sub[sub[key] != ""].groupby(key, as_index=False)["accepted quantity"].sum()
                .rename(columns={"accepted quantity": name})
            )

        open_po_by_asin    = _po_agg("open po",    "_asin", "open_po_asin")
        open_po_by_sku     = _po_agg("open po",    "_sku",  "open_po_sku")
        in_transit_by_asin = _po_agg("in-transit", "_asin", "in_transit_asin")
        in_transit_by_sku  = _po_agg("in-transit", "_sku",  "in_transit_sku")

        # =========================
        # RENAME MASTER COLUMNS
        # =========================

        master_df = master_df.rename(columns={
            "product type": "hazmat_type",
            "hazmat type": "hazmat_type",
        })

        # =========================
        # MERGE — ASIN → SKU → Model cascade on master
        # =========================
        df = master_df.copy()
        df["_asin"] = df["asin"].astype(str).str.strip().str.upper() if "asin" in df.columns else ""
        df["_sku"]  = df["sku"].astype(str).str.strip().str.upper()  if "sku"  in df.columns else ""

        # Sales
        df = df.merge(cb_sales_by_asin,     left_on="_asin", right_on="_asin", how="left")
        df = df.merge(cb_sales_by_sku,      left_on="_sku",  right_on="_sku",  how="left")
        df = df.merge(cb_sales_by_model,    on="model", how="left")
        df = df.merge(amazon_sales_by_asin, left_on="_asin", right_on="_asin", how="left")
        df = df.merge(amazon_sales_by_sku,  left_on="_sku",  right_on="_sku",  how="left")
        df = df.merge(amazon_sales_by_model,on="model", how="left")
        df["cb_3m_sales"]     = df["cb_3m_sales_asin"].fillna(df["cb_3m_sales_sku"]).fillna(df["cb_3m_sales_model"]).fillna(0)
        df["amazon_3m_sales"] = df["amazon_3m_sales_asin"].fillna(df["amazon_3m_sales_sku"]).fillna(df["amazon_3m_sales_model"]).fillna(0)

        # 1P inventory
        df = df.merge(inv_1p_by_asin,  left_on="_asin", right_on="_asin", how="left")
        df = df.merge(inv_1p_by_model, on="model", how="left")
        df["final_cb_qty"] = df["final_cb_qty_asin"].fillna(df["final_cb_qty_model"]).fillna(0)

        # AMPM
        df = df.merge(ampm_by_asin, left_on="_asin", right_on="_asin", how="left")
        df = df.merge(ampm_by_sku,  left_on="_sku",  right_on="_sku",  how="left")
        df["ampm_inventory"] = df["ampm_inventory_asin"].fillna(df["ampm_inventory_sku"]).fillna(0)

        # PO
        df = df.merge(open_po_by_asin,    left_on="_asin", right_on="_asin", how="left")
        df = df.merge(open_po_by_sku,     left_on="_sku",  right_on="_sku",  how="left")
        df = df.merge(in_transit_by_asin, left_on="_asin", right_on="_asin", how="left")
        df = df.merge(in_transit_by_sku,  left_on="_sku",  right_on="_sku",  how="left")
        df["open_po"]    = df["open_po_asin"].fillna(df["open_po_sku"]).fillna(0)
        df["in_transit"] = df["in_transit_asin"].fillna(df["in_transit_sku"]).fillna(0)

        df = df.drop(columns=[c for c in [
            "_asin", "_sku",
            "cb_3m_sales_asin", "cb_3m_sales_sku", "cb_3m_sales_model",
            "amazon_3m_sales_asin", "amazon_3m_sales_sku", "amazon_3m_sales_model",
            "final_cb_qty_asin", "final_cb_qty_model",
            "ampm_inventory_asin", "ampm_inventory_sku",
            "open_po_asin", "open_po_sku",
            "in_transit_asin", "in_transit_sku",
        ] if c in df.columns])

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