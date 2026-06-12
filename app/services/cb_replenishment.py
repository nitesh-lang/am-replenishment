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
        # CB SALES (1p Sales channel) — ASIN primary, SKU fallback, model
        # fallback. weekly_sales_snapshot.csv now ships with an `asin` column
        # (added 2026-05-28). ASIN-keyed attribution avoids the duplicate-
        # Model double-count on the 22 CB master rows where 2 SKUs share a
        # Model name.
        # =========================
        sales_df["_asin"] = sales_df.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
        sales_df["_sku"]  = sales_df["sku"].astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})

        # Each cascade level contains only the sales rows that couldn't be
        # attributed by a higher-priority key — guarantees each sales row is
        # counted exactly once across the cascade.
        def _sales_agg(channel: str, level: str, out_name: str) -> pd.DataFrame:
            sub = sales_df[sales_df["channel"] == channel]
            if level == "asin":
                sub = sub[sub["_asin"] != ""]
                grouped = sub.groupby("_asin", as_index=False)["units_sold"].sum()
            elif level == "sku":
                sub = sub[(sub["_asin"] == "") & (sub["_sku"] != "")]
                grouped = sub.groupby("_sku", as_index=False)["units_sold"].sum()
            else:  # model_join — only rows that have neither ASIN nor SKU
                sub = sub[(sub["_asin"] == "") & (sub["_sku"] == "")]
                grouped = sub.groupby(["brand", "model_join"], as_index=False)["units_sold"].sum()
            return grouped.rename(columns={"units_sold": out_name})

        cb_sales_by_asin    = _sales_agg("1p Sales", "asin",       "cb_3m_sales_asin")
        cb_sales_by_sku     = _sales_agg("1p Sales", "sku",        "cb_3m_sales_sku")
        cb_sales_by_model   = _sales_agg("1p Sales", "model_join", "cb_3m_sales_model")

        cambium_sales_by_asin  = _sales_agg("Amazon", "asin",       "cambium_3m_sales_asin")
        cambium_sales_by_sku   = _sales_agg("Amazon", "sku",        "cambium_3m_sales_sku")
        cambium_sales_by_model = _sales_agg("Amazon", "model_join", "cambium_3m_sales_model")

        # =========================
        # INVENTORY — AMPM + China Pipeline aggregated by ASIN (primary)
        # and SKU (fallback). Avoids duplicate-Model double-count: the same
        # AMPM pool was being attributed to every master row sharing a Model.
        # =========================
        ampm_by_asin   = pd.DataFrame(columns=["asin", "ampm_inventory_asin"])
        ampm_by_sku    = pd.DataFrame(columns=["sku",  "ampm_inventory_sku"])
        pipe_by_asin   = pd.DataFrame(columns=["asin", "china_in_transit_asin"])
        pipe_by_sku    = pd.DataFrame(columns=["sku",  "china_in_transit_sku"])

        if "channel" in inventory_df.columns:
            print("UNIQUE CHANNELS IN INVENTORY:", inventory_df["channel"].str.strip().unique().tolist())

            ampm_raw = inventory_df[
                inventory_df["channel"].str.strip().str.lower() == "ampm"
            ].copy()
            print("AMPM ROWS FOUND:", len(ampm_raw))

            if "qty" in ampm_raw.columns and len(ampm_raw) > 0:
                ampm_raw["_asin"] = ampm_raw.get("asin", "").astype(str).str.strip().str.upper()
                ampm_raw["_sku"]  = ampm_raw.get("sku", "").astype(str).str.strip().str.upper()
                ampm_by_asin = (
                    ampm_raw[ampm_raw["_asin"] != ""]
                    .groupby("_asin", as_index=False)["qty"].sum()
                    .rename(columns={"qty": "ampm_inventory_asin", "_asin": "asin"})
                )
                ampm_by_sku = (
                    ampm_raw[ampm_raw["_sku"] != ""]
                    .groupby("_sku", as_index=False)["qty"].sum()
                    .rename(columns={"qty": "ampm_inventory_sku", "_sku": "sku"})
                )

            # =========================
            # CHINA IN-TRANSIT (Pipeline channel from inventory snapshots)
            # Pipeline records can have missing ASIN/SKU (stock arriving from
            # China before final IDs are assigned), so we cascade through
            # ASIN -> SKU -> model_join to make sure no quantity is dropped.
            # =========================
            pipeline_raw = inventory_df[
                inventory_df["channel"].str.strip().str.lower() == "pipeline"
            ].copy()

            pipe_by_model = pd.DataFrame(columns=["model_join", "china_in_transit_model"])

            if "qty" in pipeline_raw.columns and len(pipeline_raw) > 0:
                pipeline_raw["_asin"] = pipeline_raw.get("asin", "").astype(str).str.strip().str.upper()
                pipeline_raw["_sku"]  = pipeline_raw.get("sku", "").astype(str).str.strip().str.upper()
                pipeline_raw["model_join"] = pipeline_raw["model"].astype(str).str.split("(").str[0].str.strip().str.lower()
                # Cascade levels must be EXCLUSIVE — each Pipeline row counts
                # at exactly one level. Without this, the Model fallback would
                # re-attribute Pipeline qty already counted via ASIN to every
                # duplicate-Model master row sharing that Model (the 22 CB
                # duplicate-Model pairs would each double-count).
                # SKU non-exclusive (catches ASIN-drift cases where master.ASIN
                # differs from file.ASIN but SKU still matches). Model fallback
                # stays exclusive — only rows with no ASIN AND no SKU — so
                # duplicate-Model master rows don't double-count the shared pool.
                pipe_by_asin = (
                    pipeline_raw[pipeline_raw["_asin"] != ""]
                    .groupby("_asin", as_index=False)["qty"].sum()
                    .rename(columns={"qty": "china_in_transit_asin", "_asin": "asin"})
                )
                pipe_by_sku = (
                    pipeline_raw[pipeline_raw["_sku"] != ""]
                    .groupby("_sku", as_index=False)["qty"].sum()
                    .rename(columns={"qty": "china_in_transit_sku", "_sku": "sku"})
                )
                pipe_by_model = (
                    pipeline_raw[(pipeline_raw["_asin"] == "") & (pipeline_raw["_sku"] == "")]
                    .groupby("model_join", as_index=False)["qty"].sum()
                    .rename(columns={"qty": "china_in_transit_model"})
                )
                print("PIPELINE (China In-Transit) ROWS FOUND:", len(pipeline_raw))

            inventory_df = inventory_df[
                inventory_df["channel"].str.lower() == "1p"
            ]

        # Group 1P inventory. The 1p channel rows ship with ASIN populated
        # but Model often NaN (Cambium 1P feed doesn't include Model). Pandas
        # groupby drops rows where ANY key is NaN, so we have to either group
        # on the always-populated keys OR pass dropna=False. We use the ASIN
        # path when ASIN exists; the merge downstream is on `asin` only, so
        # model isn't needed in the group key. Bug discovered 2026-06-10 —
        # previously all 1p rows were silently dropped, making final_cb_qty
        # 0 for every SKU.
        if "asin" in inventory_df.columns:
            inventory_df = (
                inventory_df.groupby(["brand", "asin"], as_index=False, dropna=False)
                .sum(numeric_only=True)
            )
            # Re-add a placeholder model column so model_join below doesn't KeyError
            if "model" not in inventory_df.columns:
                inventory_df["model"] = ""
        else:
            inventory_df = (
                inventory_df.groupby(["brand", "model"], as_index=False, dropna=False)
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

        # Aggregate PO by ASIN (primary) and SKU (fallback) — joining by Model
        # double-counts when master has multiple SKUs sharing the same Model
        # name (e.g. AM-S1 has 2 rows: same Model, different SKUs/ASINs).
        # ASIN is preferred because it's the Amazon-level product identity
        # and is unique across the CB master.
        po_df["_asin"] = po_df["asin"].astype(str).str.strip().str.upper()
        po_df["_sku"]  = po_df["sku"].astype(str).str.strip().str.upper()

        def _agg(po_subset: pd.DataFrame, key: str, name: str) -> pd.DataFrame:
            return (
                po_subset.groupby(key, as_index=False)["accepted quantity"]
                .sum()
                .rename(columns={"accepted quantity": name})
            )

        open_po_subset    = po_df[po_df["_status"] == "open po"]
        in_transit_subset = po_df[po_df["_status"] == "in-transit"]

        open_po_by_asin    = _agg(open_po_subset,    "_asin", "open_po_asin")
        open_po_by_sku     = _agg(open_po_subset,    "_sku",  "open_po_sku")
        in_transit_by_asin = _agg(in_transit_subset, "_asin", "in_transit_asin")
        in_transit_by_sku  = _agg(in_transit_subset, "_sku",  "in_transit_sku")

        # =========================
        # MERGE
        # =========================

        master_df = master_df.rename(columns={
            "hazmat type": "hazmat_type",
        })

        # Drop static china_in_transit from master — now sourced from Pipeline inventory
        if "china in transit" in master_df.columns:
            master_df = master_df.drop(columns=["china in transit"])

        df = master_df.copy()

        # Build ASIN/SKU keys on the master once — reused by every merge below.
        # The standard across CB is ASIN primary, SKU fallback (then model_join
        # for sales-rows-without-SKU only).
        df["_asin"] = df["asin"].astype(str).str.strip().str.upper()
        df["_sku"]  = df["sku"].astype(str).str.strip().str.upper()

        # --- Sales (1p + Amazon) — ASIN primary, SKU fallback, model fallback ---
        df = df.merge(cb_sales_by_asin,       left_on="_asin", right_on="_asin", how="left")
        df = df.merge(cb_sales_by_sku,        left_on="_sku",  right_on="_sku",  how="left")
        df = df.merge(cb_sales_by_model,      on=["brand", "model_join"], how="left")
        df = df.merge(cambium_sales_by_asin,  left_on="_asin", right_on="_asin", how="left")
        df = df.merge(cambium_sales_by_sku,   left_on="_sku",  right_on="_sku",  how="left")
        df = df.merge(cambium_sales_by_model, on=["brand", "model_join"], how="left")
        df["cb_3m_sales"] = (
            df["cb_3m_sales_asin"].fillna(df["cb_3m_sales_sku"]).fillna(df["cb_3m_sales_model"]).fillna(0)
        )
        df["cambium_3m_sales"] = (
            df["cambium_3m_sales_asin"].fillna(df["cambium_3m_sales_sku"]).fillna(df["cambium_3m_sales_model"]).fillna(0)
        )

        # --- 1P inventory — already ASIN-keyed (or brand+model fallback) ---
        if "asin" in inventory_df.columns:
            df = df.merge(inventory_df[["asin","final_cb_qty"]], on="asin", how="left")
        else:
            df = df.merge(inventory_df[["brand","model_join","final_cb_qty"]], on=["brand","model_join"], how="left")

        # --- AMPM inventory — ASIN primary, SKU fallback ---
        df = df.merge(ampm_by_asin, left_on="_asin", right_on="asin", how="left", suffixes=("", "_ampm_a"))
        df = df.merge(ampm_by_sku,  left_on="_sku",  right_on="sku",  how="left", suffixes=("", "_ampm_s"))
        df["ampm_inventory"] = df["ampm_inventory_asin"].fillna(df["ampm_inventory_sku"]).fillna(0)

        # --- China in-transit (Pipeline) — ASIN -> SKU -> Model cascade ---
        # Model fallback included because Pipeline records frequently arrive
        # from China without final ASIN/SKU yet; without this, those units
        # disappear from the deficiency calc.
        df = df.merge(pipe_by_asin,  left_on="_asin", right_on="asin", how="left", suffixes=("", "_pipe_a"))
        df = df.merge(pipe_by_sku,   left_on="_sku",  right_on="sku",  how="left", suffixes=("", "_pipe_s"))
        df = df.merge(pipe_by_model, on="model_join", how="left")
        df["china_in_transit"] = (
            df["china_in_transit_asin"]
            .fillna(df["china_in_transit_sku"])
            .fillna(df["china_in_transit_model"])
            .fillna(0)
        )

        # --- PO (Open + In-Transit) — ASIN primary, SKU fallback ---
        df = df.merge(open_po_by_asin,    on="_asin", how="left")
        df = df.merge(open_po_by_sku,     on="_sku",  how="left")
        df = df.merge(in_transit_by_asin, on="_asin", how="left")
        df = df.merge(in_transit_by_sku,  on="_sku",  how="left")
        df["open_po"]    = df["open_po_asin"].fillna(df["open_po_sku"]).fillna(0)
        df["in_transit"] = df["in_transit_asin"].fillna(df["in_transit_sku"]).fillna(0)

        # Drop helper / lookup columns
        df = df.drop(columns=[c for c in [
            "_asin", "_sku",
            "cb_3m_sales_asin", "cb_3m_sales_sku", "cb_3m_sales_model",
            "cambium_3m_sales_asin", "cambium_3m_sales_sku", "cambium_3m_sales_model",
            "ampm_inventory_asin", "ampm_inventory_sku",
            "china_in_transit_asin", "china_in_transit_sku", "china_in_transit_model",
            "open_po_asin", "open_po_sku",
            "in_transit_asin", "in_transit_sku",
            "asin_ampm_a", "sku_ampm_s", "asin_pipe_a", "sku_pipe_s",
        ] if c in df.columns])

        df = df.fillna(0)
        df["remarks"] = ""

        # =========================
        # CALCULATIONS
        # Uses window_size (from_week → to_week) for avg weekly sales
        # Uses cover_weeks for estimated_qty
        # =========================

        df["total_sales"] = df["cb_3m_sales"] + df["cambium_3m_sales"]

        df["avg_weekly_sales"] = df["total_sales"] / window_size

        # =========================
        # LAST 2 WEEKS TOP — CB-specific recency-based velocity bump
        # When the most-recent 2 weeks' weekly avg exceeds the window avg,
        # use that higher number for estimated_qty so recent spikes flow
        # through to PO Req. Combined 1p Sales + Amazon channels.
        # =========================
        if "week" in sales_df.columns and len(sales_df) > 0:
            weeks_desc = sorted(
                pd.to_numeric(sales_df["week"], errors="coerce").dropna().unique(),
                reverse=True,
            )
            last_2_weeks = weeks_desc[:2]
            l2_src = sales_df[sales_df["week"].isin(last_2_weeks)].copy()
            l2_src = l2_src[l2_src["channel"].isin(["1p Sales", "Amazon"])]

            l2_src["_asin"] = l2_src.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
            l2_src["_sku"]  = l2_src["sku"].astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})

            l2_by_asin = (
                l2_src[l2_src["_asin"] != ""]
                .groupby("_asin", as_index=False)["units_sold"].sum()
                .rename(columns={"units_sold": "_l2_units_asin"})
            )
            l2_by_sku = (
                l2_src[(l2_src["_asin"] == "") & (l2_src["_sku"] != "")]
                .groupby("_sku", as_index=False)["units_sold"].sum()
                .rename(columns={"units_sold": "_l2_units_sku"})
            )
            l2_by_model = (
                l2_src[(l2_src["_asin"] == "") & (l2_src["_sku"] == "")]
                .groupby(["brand", "model_join"], as_index=False)["units_sold"].sum()
                .rename(columns={"units_sold": "_l2_units_model"})
            )

            df["_asin"] = df["asin"].astype(str).str.strip().str.upper()
            df["_sku"]  = df["sku"].astype(str).str.strip().str.upper()
            df = df.merge(l2_by_asin,  on="_asin", how="left")
            df = df.merge(l2_by_sku,   on="_sku",  how="left")
            df = df.merge(l2_by_model, on=["brand", "model_join"], how="left")
            df["last_2w_units"] = (
                df["_l2_units_asin"]
                .fillna(df["_l2_units_sku"])
                .fillna(df["_l2_units_model"])
                .fillna(0)
            )
            n_last = max(len(last_2_weeks), 1)
            df["last_2_velocity"] = (df["last_2w_units"] / n_last).round(2)
        else:
            df["last_2w_units"]   = 0.0
            df["last_2_velocity"] = 0.0

        # MAX(window, last-2-week) so estimated_qty captures recent surges
        df["window_velocity"]    = df["avg_weekly_sales"]
        df["effective_velocity"] = df[["window_velocity", "last_2_velocity"]].max(axis=1)
        df["velocity_basis"]     = "window"
        df.loc[df["last_2_velocity"] > df["window_velocity"], "velocity_basis"] = "2wk"

        df["estimated_qty"] = (df["effective_velocity"] * cover_weeks).round()

        df = df.drop(columns=[c for c in [
            "_asin", "_sku", "_l2_units_asin", "_l2_units_sku", "_l2_units_model",
        ] if c in df.columns])

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
