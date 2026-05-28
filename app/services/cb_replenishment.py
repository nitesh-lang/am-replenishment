import pandas as pd
from pathlib import Path
from app.services.file_cache import get

DATA_PATH = Path("data/input")

def load_cb_replenishment(from_week: int = 52, to_week: int = 11, cover_weeks: int = 8):
    """
    from_week   : start of sales window (inclusive), default 1
    to_week     : end   of sales window (inclusive), default 11
    cover_weeks : weeks of cover for estimated_qty,  default 8
    """

    try:

        # =========================
        # LOAD FILES
        # =========================

        master_df = get("CB Replenishment_Master.xlsx")
        sales_df = get("weekly_sales_snapshot.csv")
        inv_audio_df = get("Inventory_snapshot_audio_array.xlsx")
        inv_tonor_df = get("Inventory_snapshot_tonor.xlsx")
        po_df = get("In_Transit_PO data.xlsx")

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
            df["brand"] = df["brand"].astype(str).str.strip().str.title()
            df["model"] = df["model"].astype(str).str.strip()

        # Normalize master model names for joining — strip bundle descriptions like "UB-01 (AI-04...)"
        # Case-insensitive: lowercased so master "AM-W47 Wired" matches inventory "AM-W47 WIRED".
        master_df["model_join"] = master_df["model"].astype(str).str.split("(").str[0].str.strip().str.lower()
        sales_df["model_join"]  = sales_df["model"].astype(str).str.split("(").str[0].str.strip().str.lower()

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
            sales_df["week"] = (
                sales_df["week"].astype(str)
                .str.extract(r"(\d+)")[0]
                .pipe(pd.to_numeric, errors="coerce")
            )

            # Get last 12 weeks available in data (sorted descending)
            available_weeks = sorted(
                sales_df["week"].dropna().unique().tolist(),
                reverse=True
            )[:12]

            # Filter to selected from/to within available weeks
            if from_week in available_weeks and to_week in available_weeks:
                from_idx = available_weeks.index(from_week)
                to_idx = available_weeks.index(to_week)
                # from_idx >= to_idx since list is descending
                selected_weeks = available_weeks[to_idx:from_idx + 1]
            else:
                selected_weeks = available_weeks

            sales_df = sales_df[sales_df["week"].isin(selected_weeks)]
            window_size = max(len(selected_weeks), 1)

        # =========================
        # CB SALES
        # =========================

        cb_sales = (
            sales_df[sales_df["channel"] == "1p Sales"]
            .groupby(["brand", "model_join"], as_index=False)["units_sold"]
            .sum()
            .rename(columns={"units_sold": "cb_3m_sales"})
        )

        # =========================
        # CAMBIUM SALES
        # =========================

        cambium_sales = (
            sales_df[sales_df["channel"] == "Amazon"]
            .groupby(["brand", "model_join"], as_index=False)["units_sold"]
            .sum()
            .rename(columns={"units_sold": "cambium_3m_sales"})
        )

        # =========================
        # INVENTORY
        # =========================
        ampm_inventory_df = pd.DataFrame(columns=["brand", "model_join", "ampm_inventory"])
        china_in_transit_df = pd.DataFrame(columns=["model_join", "china_in_transit"])

        if "channel" in inventory_df.columns:
            print("UNIQUE CHANNELS IN INVENTORY:", inventory_df["channel"].str.strip().unique().tolist())

            ampm_raw = inventory_df[
                inventory_df["channel"].str.strip().str.lower() == "ampm"
            ].groupby(["brand", "model"], as_index=False).sum(numeric_only=True)

            print("AMPM ROWS FOUND:", len(ampm_raw))

            if "qty" in ampm_raw.columns and len(ampm_raw) > 0:
                ampm_raw["model_join"] = ampm_raw["model"].astype(str).str.split("(").str[0].str.strip().str.lower()
                ampm_inventory_df = ampm_raw.rename(columns={"qty": "ampm_inventory"})[["brand", "model_join", "ampm_inventory"]]

            # =========================
            # CHINA IN-TRANSIT (Pipeline channel from inventory snapshots)
            # =========================
            pipeline_raw = inventory_df[
                inventory_df["channel"].str.strip().str.lower() == "pipeline"
            ].copy()

            if "qty" in pipeline_raw.columns and len(pipeline_raw) > 0:
                pipeline_raw["model_join"] = pipeline_raw["model"].astype(str).str.split("(").str[0].str.strip().str.lower()
                china_in_transit_df = (
                    pipeline_raw.groupby("model_join", as_index=False)["qty"]
                    .sum()
                    .rename(columns={"qty": "china_in_transit"})
                )
                print("PIPELINE (China In-Transit) ROWS FOUND:", len(china_in_transit_df))

            inventory_df = inventory_df[
                inventory_df["channel"].str.lower() == "1p"
            ]

        # Group 1P inventory by ASIN — one model can have multiple ASINs
        if "asin" in inventory_df.columns:
            inventory_df = (
                inventory_df.groupby(["brand", "model", "asin"], as_index=False)
                .sum(numeric_only=True)
            )
        else:
            inventory_df = (
                inventory_df.groupby(["brand", "model"], as_index=False)
                .sum(numeric_only=True)
            )
        inventory_df["model_join"] = inventory_df["model"].astype(str).str.split("(").str[0].str.strip().str.lower()

        if "qty" in inventory_df.columns:
            inventory_df = inventory_df.rename(
                columns={"qty": "final_cb_qty"}
            )

        # =========================
        # OPEN PO / IN TRANSIT
        # =========================

        po_df["model_join"] = po_df["model"].astype(str).str.split("(").str[0].str.strip().str.lower()

        # Case-insensitive Delivery Status — the source file uses "Open po"
        # (lowercase) and "In-Transit" inconsistently. Normalise before filter.
        po_df["_status"] = po_df["delivery status"].astype(str).str.strip().str.lower()

        open_po = (
            po_df[po_df["_status"] == "open po"]
            .groupby("model_join", as_index=False)["accepted quantity"]
            .sum()
            .rename(columns={"accepted quantity": "open_po"})
        )

        in_transit = (
            po_df[po_df["_status"] == "in-transit"]
            .groupby("model_join", as_index=False)["accepted quantity"]
            .sum()
            .rename(columns={"accepted quantity": "in_transit"})
        )

        # =========================
        # MERGE
        # =========================

        master_df = master_df.rename(columns={
            "hazmat type": "hazmat_type",
        })

        # Drop static china_in_transit from master — now sourced from Pipeline inventory
        if "china in transit" in master_df.columns:
            master_df = master_df.drop(columns=["china in transit"])

        df = master_df.merge(cb_sales, on=["brand","model_join"], how="left")
        df = df.merge(cambium_sales, on=["brand","model_join"], how="left")
        if "asin" in inventory_df.columns:
            df = df.merge(inventory_df[["asin","final_cb_qty"]], on="asin", how="left")
        else:
            df = df.merge(inventory_df[["brand","model_join","final_cb_qty"]], on=["brand","model_join"], how="left")
        df = df.merge(ampm_inventory_df[["brand","model_join","ampm_inventory"]], on=["brand","model_join"], how="left")
        df = df.merge(china_in_transit_df, on="model_join", how="left")
        df = df.merge(open_po, on="model_join", how="left")
        df = df.merge(in_transit, on="model_join", how="left")

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

        # Cap PO requirement at AMPM (mother warehouse) stock — can't ship more
        # than what AMPM physically has. Applied BEFORE the DB merge so any
        # user-saved override in cb_inputs still wins below.
        df["po_requirement"] = df[["po_requirement", "ampm_inventory"]].min(axis=1)

        # =========================
        # DB MERGE (remarks only)
        # =========================

        from app.services.db import get_conn

        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cb_inputs (
                        model TEXT PRIMARY KEY,
                        po_requirement INTEGER DEFAULT 0,
                        remarks TEXT DEFAULT ''
                    )
                """)
                cursor.execute("ALTER TABLE cb_inputs ADD COLUMN IF NOT EXISTS po_requirement INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE cb_inputs ADD COLUMN IF NOT EXISTS remarks TEXT DEFAULT ''")
            conn.commit()

            # Load po_requirement and remarks — DB value wins if user saved it
            db_df = pd.read_sql("SELECT model, po_requirement, remarks FROM cb_inputs", conn)

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
                df["remarks"] = df["remarks_db"].fillna("")
                df = df.drop(columns=["remarks_db"], errors="ignore")

        return df

    except Exception as e:

        print("CB REPLENISHMENT ERROR:", str(e))

        return pd.DataFrame()
