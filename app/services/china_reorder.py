import os
import pandas as pd
from app.services.file_cache import get, get_excel_sheet


# =================================================
# ADDITIONAL DATA LOADERS (used by China Reorder /
# Reorder Intelligence — joined by ASIN)
# =================================================

_REVIEW_FILES = [
    "Additional/reviews/Audio Array.csv",
    "Additional/reviews/Nexlev.csv",
    "Additional/reviews/Tonor.csv",
    "Additional/reviews/White Mulberry.csv",
]

_MARGIN_FILES = [
    # (path, sheet name)
    ("Additional/margin/Audio Array.xlsx",    "Margin Data"),
    ("Additional/margin/Nexlev.xlsx",         "Margin Data"),
    ("Additional/margin/White Mulberry.xlsx", "Margin Data"),
]

_FBA_RETURN_FILES = [
    "Additional/returns/Audio Array FBA Returns.csv",
    "Additional/returns/Nexlev.csv",
    "Additional/returns/CRPL.csv",
    "Additional/returns/viomi.csv",
]

_1P_RETURN_FILE = "Additional/returns/1p Returns.xlsx"


def _load_reviews_by_asin() -> pd.DataFrame:
    """ASIN → (avg_rating, rating_count). Pooled across brand files."""
    parts = []
    for f in _REVIEW_FILES:
        try:
            df = get(f)
        except Exception as e:
            print(f"⚠️ reviews not loaded ({f}): {e}")
            continue
        if "ASIN" not in df.columns:
            continue
        df = df.copy()
        df["_asin"] = df["ASIN"].astype(str).str.strip().str.upper()
        cols = {"_asin": "asin"}
        if "Reviews: Rating"       in df.columns: cols["Reviews: Rating"]       = "avg_rating"
        if "Reviews: Rating Count" in df.columns: cols["Reviews: Rating Count"] = "rating_count"
        parts.append(df.rename(columns=cols)[list(cols.values())])
    if not parts:
        return pd.DataFrame(columns=["asin", "avg_rating", "rating_count"])
    out = pd.concat(parts, ignore_index=True).drop_duplicates(subset=["asin"], keep="first")
    return out


def _load_margin_by_asin() -> pd.DataFrame:
    """ASIN → (net_margin_inr, net_margin_pct). Pooled across brand files."""
    parts = []
    for f, sheet in _MARGIN_FILES:
        try:
            df = get_excel_sheet(f, sheet)
        except Exception as e:
            print(f"⚠️ margin not loaded ({f}::{sheet}): {e}")
            continue
        if "ASIN" not in df.columns:
            continue
        df = df.copy()
        df["_asin"] = df["ASIN"].astype(str).str.strip().str.upper()
        cols = {"_asin": "asin"}
        if "Net Margin"   in df.columns: cols["Net Margin"]   = "net_margin_inr"
        if "Net Margin %" in df.columns: cols["Net Margin %"] = "net_margin_pct"
        parts.append(df.rename(columns=cols)[list(cols.values())])
    if not parts:
        return pd.DataFrame(columns=["asin", "net_margin_inr", "net_margin_pct"])
    out = pd.concat(parts, ignore_index=True).drop_duplicates(subset=["asin"], keep="first")
    return out


def _load_returns_by_asin() -> pd.DataFrame:
    """ASIN → returns_90d.

    FBA returns: row-level with `return-date` — filter to last 90 days,
    sum `quantity` per ASIN.
    1p Returns: ASIN-level summary already (~90-day viewing range in
    the file's banner), take the `Customer Returns` column directly.
    """
    cutoff = pd.Timestamp.now(tz="UTC").tz_localize(None) - pd.Timedelta(days=90)
    parts = []

    # FBA per-event returns
    for f in _FBA_RETURN_FILES:
        try:
            df = get(f)
        except Exception as e:
            print(f"⚠️ FBA returns not loaded ({f}): {e}")
            continue
        if not {"asin", "return-date", "quantity"}.issubset(df.columns):
            continue
        df = df.copy()
        df["_dt"]  = pd.to_datetime(df["return-date"], errors="coerce", utc=True).dt.tz_localize(None)
        df["_qty"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
        df = df[df["_dt"] >= cutoff]
        df["_asin"] = df["asin"].astype(str).str.strip().str.upper()
        parts.append(df[["_asin", "_qty"]].rename(columns={"_asin": "asin", "_qty": "returns_90d"}))

    # 1p returns (ASIN-level pre-aggregated)
    try:
        df1 = get_excel_sheet(_1P_RETURN_FILE, "Sheet1", header=1) if False else None
    except Exception:
        df1 = None
    # The 1p file has a non-standard banner — try multiple read strategies
    try:
        df1 = pd.read_excel(
            f"data/input/{_1P_RETURN_FILE}", sheet_name=0, engine="openpyxl", header=1
        )
        if "ASIN" in df1.columns and "Customer Returns" in df1.columns:
            df1 = df1.copy()
            df1["asin"]        = df1["ASIN"].astype(str).str.strip().str.upper()
            df1["returns_90d"] = pd.to_numeric(df1["Customer Returns"], errors="coerce").fillna(0)
            parts.append(df1[["asin", "returns_90d"]])
    except Exception as e:
        print(f"⚠️ 1p returns not loaded: {e}")

    if not parts:
        return pd.DataFrame(columns=["asin", "returns_90d"])

    return (
        pd.concat(parts, ignore_index=True)
          .groupby("asin", as_index=False)["returns_90d"].sum()
    )


def china_reorder_logic(
    brand: str = "Nexlev",
    months: int = 3,
    channel: str = None,
    from_week=None,
    to_week=None,
):

    # ============================================================
    # BASE DIRECTORY
    # ============================================================

    BASE_DIR = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )

    # ============================================================
    # SALES FILE (COMMON)
    # ============================================================

    sales_path = os.path.join(
        BASE_DIR,
        "..",
        "data",
        "input",
        "weekly_sales_snapshot - ChinaReorder.csv"
    )

    # ============================================================
    # INVENTORY FILE MAP
    # ============================================================

    brand_inventory_map = {
        "nexlev": "inventory_snapshot_nexlev.xlsx",
        "audio array": "Inventory_snapshot_audio_array.xlsx",
        "tonor": "Inventory_snapshot_tonor.xlsx",
        "white mulberry": "Inventory_snapshot_WM.xlsx"
    }

    brand_clean = brand.strip().lower()

    if brand_clean not in brand_inventory_map:
        raise ValueError(f"Invalid brand received: {brand}")

    inv_file = brand_inventory_map[brand_clean]

    inv_path = os.path.join(
        BASE_DIR,
        "..",
        "data",
        "input",
        inv_file
    )

    print("READING SALES (cached): weekly_sales_snapshot - ChinaReorder.csv")
    print("READING INVENTORY (cached):", inv_file)

    # ============================================================
    # LOAD FILES
    # ============================================================

    sales_df = get("weekly_sales_snapshot - ChinaReorder.csv")
    inv_df = get(inv_file)

    # ============================================================
    # CLEAN COLUMN NAMES
    # ============================================================

    sales_df.columns = (
        sales_df.columns
        .str.strip()
        .str.lower()
    )

    inv_df.columns = (
        inv_df.columns
        .str.strip()
        .str.lower()
    )

    # ============================================================
    # CLEAN IMPORTANT FIELDS
    # ============================================================

    sales_df["brand"] = (
        sales_df["brand"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    sales_df["model"] = (
        sales_df["model"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    inv_df["model"] = (
        inv_df["model"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # Normalize sales model names — strip variant suffixes like "ETC-07-WH" → "ETC-07"
    inv_models = set(inv_df["model"].unique())
    def normalize_model(m):
        m = str(m).strip().upper()
        if m in inv_models:
            return m
        # Strip after last '-' if result matches inventory model
        parts = m.rsplit("-", 1)
        if len(parts) == 2 and parts[0] in inv_models:
            return parts[0]
        # Strip bundle description after '('
        base = m.split("(")[0].strip()
        if base in inv_models:
            return base
        return m
    sales_df["model"] = sales_df["model"].apply(normalize_model)

    inv_df["channel"] = (
        inv_df["channel"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    # ============================================================
    # BRAND FILTER
    # ============================================================

    sales_df = sales_df[
        sales_df["brand"] == brand_clean
    ]

    # ============================================================
    # SALES WINDOW FILTER
    # ============================================================

    sales_df["week_num"] = (
        sales_df["week"].astype(str)
        .str.extract(r"(\d+)")[0]
        .pipe(pd.to_numeric, errors="coerce")
    )

    available_weeks = sorted(
        sales_df["week_num"].dropna().unique().tolist(),
        reverse=True
    )[:12]

    if from_week in available_weeks and to_week in available_weeks:
        from_idx = available_weeks.index(from_week)
        to_idx = available_weeks.index(to_week)
        selected_weeks = available_weeks[to_idx:from_idx + 1]
    else:
        selected_weeks = available_weeks

    last_12 = sales_df[sales_df["week_num"].isin(selected_weeks)]
    window_size = max(len(selected_weeks), 1)

    # ============================================================
    # SALES AGGREGATION
    # ============================================================

    sales_agg = (
        last_12
        .groupby("model", as_index=False)
        .agg(last_12w_sales=("units_sold", "sum"))
    )

    sales_agg["avg_weekly_sales"] = (
        sales_agg["last_12w_sales"] / window_size
    )

    # ============================================================
    # INVENTORY SPLIT
    # ============================================================
    open_order_df = inv_df[inv_df["channel"] == "open order"]
    pipeline_df   = inv_df[inv_df["channel"] == "pipeline"]
    inventory_df  = inv_df[
        ~inv_df["channel"].isin(["open order", "pipeline"])
    ]

    # ============================================================
    # CATEGORY MAPPING (from inventory)
    # ============================================================

    cat_cols = [c for c in inv_df.columns if c.startswith("category")]
    if cat_cols:
        category_map = (
            inv_df[["model"] + cat_cols]
            .drop_duplicates(subset="model")
        )
    else:
        category_map = pd.DataFrame(columns=["model"])

    # ============================================================
    # CURRENT INVENTORY AGG
    # ============================================================

    inventory_agg = (
        inventory_df
        .groupby("model", as_index=False)
        .agg(current_inventory=("qty", "sum"))
    )

    # ============================================================
    # OPEN ORDER AGG
    # ============================================================

    open_order_agg = (
        open_order_df
        .groupby("model", as_index=False)
        .agg(open_order_qty=("qty", "sum"))
    )

    # ============================================================
    # PIPELINE AGG
    # ============================================================

    pipeline_agg = (
        pipeline_df
        .groupby("model", as_index=False)
        .agg(pipeline_qty=("qty", "sum"))
    )

    # ============================================================
    # MERGE INVENTORY + OPEN ORDER + PIPELINE
    # ============================================================

    inv_agg = pd.merge(inventory_agg, open_order_agg, on="model", how="outer")
    inv_agg = pd.merge(inv_agg, pipeline_agg, on="model", how="outer")
    inv_agg = inv_agg.fillna(0)

    # ============================================================
    # FINAL MERGE (SALES + INVENTORY)
    # ============================================================

    df = pd.merge(sales_agg, inv_agg, on="model", how="outer").fillna(0)

    # Merge category columns
    if not category_map.empty and len(category_map.columns) > 1:
        df = df.merge(category_map, on="model", how="left")
        for col in cat_cols:
            df[col] = df[col].fillna("")

    # ============================================================
    # ENSURE NUMERIC TYPES
    # ============================================================

    df["avg_weekly_sales"] = pd.to_numeric(
        df["avg_weekly_sales"],
        errors="coerce"
    ).fillna(0)

    df["current_inventory"] = pd.to_numeric(
        df["current_inventory"],
        errors="coerce"
    ).fillna(0)

    df["open_order_qty"] = pd.to_numeric(
        df["open_order_qty"],
        errors="coerce"
    ).fillna(0)

    # ============================================================
    # CALCULATIONS
    # ============================================================

    target_weeks = months * 4

    df["weeks_cover"] = df.apply(
        lambda row:
        row["current_inventory"] / row["avg_weekly_sales"]
        if row["avg_weekly_sales"] > 0 else 0,
        axis=1
    )

    df["target_stock"] = (
        df["avg_weekly_sales"] * target_weeks
    )

    df["suggested_reorder"] = (
        df["target_stock"] - df["current_inventory"] - df["open_order_qty"] - df["pipeline_qty"]
    ).clip(lower=0)

    # ============================================================
    # ASIN MAP (from inventory) + ADDITIONAL DATA LOOKUPS
    # ============================================================
    # Reviews, margin, and returns are all keyed on ASIN. Build a
    # model -> asin map from the brand's inventory snapshot, then merge
    # the three extra datasets in.
    asin_col = None
    for cand in ["asin", "ASIN"]:
        if cand in inv_df.columns:
            asin_col = cand; break
    if asin_col is not None:
        model_asin = (
            inv_df[["model", asin_col]]
            .dropna()
            .drop_duplicates(subset="model")
            .rename(columns={asin_col: "asin"})
        )
        model_asin["asin"] = model_asin["asin"].astype(str).str.strip().str.upper()
        df = df.merge(model_asin, on="model", how="left")
    else:
        df["asin"] = ""
    df["asin"] = df["asin"].fillna("").astype(str)

    # Reviews
    rev = _load_reviews_by_asin()
    df = df.merge(rev, on="asin", how="left")
    df["avg_rating"]   = pd.to_numeric(df.get("avg_rating",   0), errors="coerce").fillna(0).round(1)
    df["rating_count"] = pd.to_numeric(df.get("rating_count", 0), errors="coerce").fillna(0).astype(int)

    # Margin
    mar = _load_margin_by_asin()
    df = df.merge(mar, on="asin", how="left")
    df["net_margin_inr"] = pd.to_numeric(df.get("net_margin_inr", 0), errors="coerce").fillna(0).round(0).astype(int)
    df["net_margin_pct"] = pd.to_numeric(df.get("net_margin_pct", 0), errors="coerce").fillna(0).round(2)

    # Returns — qty over last 90 days; % against 12-week sales
    ret = _load_returns_by_asin()
    df = df.merge(ret, on="asin", how="left")
    df["returns_90d"] = pd.to_numeric(df.get("returns_90d", 0), errors="coerce").fillna(0).astype(int)
    df["returns_pct"] = df.apply(
        lambda r: round((r["returns_90d"] / r["last_12w_sales"]) * 100, 2)
                  if r.get("last_12w_sales", 0) > 0 else 0.0,
        axis=1,
    )

    # ============================================================
    # OPTIONAL REMARKS COLUMN
    # ============================================================

    df["remarks"] = ""

    # ============================================================
    # JSON-SAFE SANITIZE — any lingering NaN / inf blows up json.dumps
    # ============================================================
    import numpy as np
    df = df.replace([np.inf, -np.inf], 0)
    # Numeric NaNs -> 0; object NaNs -> ""
    for c in df.columns:
        if pd.api.types.is_numeric_dtype(df[c]):
            df[c] = df[c].fillna(0)
        else:
            df[c] = df[c].fillna("").astype(str)

    # ============================================================
    # RETURN JSON
    # ============================================================

    return df.to_dict(orient="records")