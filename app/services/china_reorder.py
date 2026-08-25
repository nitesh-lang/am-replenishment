import os
from pathlib import Path
import pandas as pd
from app.services.file_cache import get, get_excel_sheet


_DATA_INPUT = Path("data/input")

# AA + Tonor 1p inventory moved out of the manual Inventory_snapshot_*.xlsx
# files (now produced by scripts/sp_vendor_soh_pull.py). China Reorder folds
# the 1p slice into `current_inventory` (anything not "open order" or
# "pipeline"), so we inject the SP-API rows into inv_df with channel='1p'
# for the affected brands. Other brands (WM, Nexlev) keep their existing
# snapshot 1p rows unchanged.
def _vendor_soh_1p_for_brand(brand_clean: str) -> pd.DataFrame:
    fname_map = {
        "audio array": "vendor_soh_audio_array.csv",
        "tonor":       "vendor_soh_tonor.csv",
    }
    fname = fname_map.get(brand_clean)
    if not fname:
        return pd.DataFrame()
    p = _DATA_INPUT / fname
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.columns = df.columns.str.strip().str.lower()
    df["channel"] = "1p"
    return df


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
    "Additional/returns/Audio Array FBA Returns.xlsx",
    "Additional/returns/Nexlev.xlsx",
    "Additional/returns/CRPL.xlsx",
    "Additional/returns/viomi.xlsx",
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
        "weekly_sales_snapshot.csv"
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

    print("READING SALES (cached): weekly_sales_snapshot.csv")
    print("READING INVENTORY (cached):", inv_file)

    # ============================================================
    # LOAD FILES
    # ============================================================

    sales_df = get("weekly_sales_snapshot.csv")
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

    # Inject SP-API 1p rows for AA + Tonor (the manual snapshots no longer
    # ship a 1p slice for these brands). No-op for other brands.
    vendor_1p = _vendor_soh_1p_for_brand(brand_clean)
    if not vendor_1p.empty:
        inv_df = pd.concat([inv_df, vendor_1p], ignore_index=True)

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

    # ============================================================
    # CANONICALIZE MODEL VIA sku_master (ASIN -> SKU -> string-normalize)
    # ============================================================
    # Build (ASIN -> Model) and (SKU -> Model) maps from sku_master filtered
    # to this brand. This handles two real problems at once:
    #   1. Spelling drift in sales data (e.g. "AH-60 RD" vs "AH-60-RD") —
    #      both ASINs map to the same canonical Model.
    #   2. Bundle / variant aliases — different SKUs sharing one Model are
    #      attributed to the same Model row in the output.
    # Sales / inventory rows without ASIN+SKU fall back to the existing
    # string-based normalization (case + variant suffix + bundle strip).
    asin_to_model: dict[str, str] = {}
    sku_to_model:  dict[str, str] = {}
    try:
        sm = get("sku_master.xlsx")
        sm = sm.dropna(subset=["FBA SKU", "Model"]).copy()
        sm.columns = sm.columns.str.strip()
        sm["_brand"] = sm["Brand"].astype(str).str.strip().str.lower()
        sm["_model_canon"] = sm["Model"].astype(str).str.strip().str.upper()
        sm["_asin"] = sm["ASIN"].astype(str).str.strip().str.upper()
        sm["_sku"]  = sm["FBA SKU"].astype(str).str.strip().str.upper()
        sm_b = sm[sm["_brand"] == brand_clean]
        # Drop dup keys — keep first occurrence
        asin_to_model = dict(zip(
            sm_b[sm_b["_asin"].str.fullmatch(r"[A-Z0-9]+", na=False)].drop_duplicates("_asin")["_asin"],
            sm_b[sm_b["_asin"].str.fullmatch(r"[A-Z0-9]+", na=False)].drop_duplicates("_asin")["_model_canon"],
        ))
        sku_to_model = dict(zip(
            sm_b[sm_b["_sku"] != ""].drop_duplicates("_sku")["_sku"],
            sm_b[sm_b["_sku"] != ""].drop_duplicates("_sku")["_model_canon"],
        ))
    except Exception as e:
        print(f"⚠️  sku_master load failed ({brand_clean}): {e}")

    # String-normalize fallback — case + variant + bundle stripping against
    # the brand's inventory models.
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

    def canonical_model(asin: str, sku: str, model: str) -> str:
        if asin and asin in asin_to_model:
            return asin_to_model[asin]
        if sku and sku in sku_to_model:
            return sku_to_model[sku]
        return normalize_model(model)

    # Apply cascade to sales
    sales_df["_asin"] = sales_df.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    sales_df["_sku"]  = sales_df.get("sku",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    sales_df["model"] = [
        canonical_model(a, s, m)
        for a, s, m in zip(sales_df["_asin"], sales_df["_sku"], sales_df["model"])
    ]

    # Apply same cascade to inventory (so the model groupby below aligns)
    inv_df["_asin"] = inv_df.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    inv_df["_sku"]  = inv_df.get("sku",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    inv_df["model"] = [
        canonical_model(a, s, m)
        for a, s, m in zip(inv_df["_asin"], inv_df["_sku"], inv_df["model"])
    ]

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

    # ============================================================
    # MASTER-SHADOW ROWS
    # If a Model exists in sku_master for this brand but has no sales
    # and no inventory (0 units across every channel), it gets silently
    # dropped from both aggregates and never appears here. Operator wants
    # every master SKU visible even at 0. Seed missing models with zero
    # rows; downstream target_stock / suggested_reorder math handles them.
    # ============================================================
    try:
        _sm = get("sku_master.xlsx")
        _sm.columns = _sm.columns.str.strip()
        _sm = _sm.dropna(subset=["Model"]).copy()
        _sm["_brand"] = _sm["Brand"].astype(str).str.strip().str.lower()
        _sm["_model"] = _sm["Model"].astype(str).str.strip().str.upper()
        _brand_models = set(
            _sm.loc[_sm["_brand"] == brand_clean, "_model"].dropna().tolist()
        )
        _existing = set(df["model"].astype(str).str.strip().str.upper().tolist())
        _missing = sorted(_brand_models - _existing)
        if _missing:
            shadow_rows = pd.DataFrame({
                "model": _missing,
                "last_12w_sales": 0,
                "avg_weekly_sales": 0.0,
                "current_inventory": 0,
                "open_order_qty": 0,
                "pipeline_qty": 0,
            })
            for c in df.columns:
                if c not in shadow_rows.columns:
                    shadow_rows[c] = 0
            df = pd.concat([df, shadow_rows[df.columns]], ignore_index=True)
    except Exception as _e:
        print(f"⚠️  master-shadow seeding failed for {brand_clean}: {_e}")

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
    # SKU + ASIN from sku_master (canonical source of truth)
    # ============================================================
    # Build a (brand, model_key) -> (FBA SKU, ASIN) lookup from sku_master,
    # then merge onto the aggregated reorder rows. sku_master is the single
    # source aligned across CB / AA / WM / Nexlev / Viomi replenishment masters
    # (see CLAUDE.md §12). Falls back to inventory-snapshot ASIN if a row
    # doesn't resolve.
    try:
        sku_master = get("sku_master.xlsx")
        sku_master.columns = sku_master.columns.str.strip()
        sku_master = sku_master.dropna(subset=["FBA SKU", "Model"]).copy()
        sku_master["_brand"] = sku_master["Brand"].astype(str).str.strip().str.lower()
        sku_master["_model"] = sku_master["Model"].astype(str).str.strip().str.upper()
        sku_master["sku"] = sku_master["FBA SKU"].astype(str).str.strip().str.upper()
        sku_master["asin_master"] = sku_master["ASIN"].astype(str).str.strip().str.upper()
        # ASIN Type (Core / Medium / Tail / New / New Launch / To be Launched /
        # EOL) — operator added the column to sku_master 2026-08-25 and wants it
        # visible per brand on the Reorder tab. Display only; drives nothing.
        # Column may be absent on an older sku_master, so guard it.
        _at = next((c for c in sku_master.columns
                    if str(c).strip().lower() == "asin type"), None)
        sku_master["asin_type"] = (
            sku_master[_at].fillna("").astype(str).str.strip() if _at else ""
        )
        master_lookup = (
            sku_master[sku_master["_brand"] == brand_clean]
            [["_model", "sku", "asin_master", "asin_type"]]
            .drop_duplicates(subset="_model", keep="first")
            .rename(columns={"_model": "model"})
        )
        df = df.merge(master_lookup, on="model", how="left")
    except Exception as e:
        print(f"⚠️  sku_master lookup failed for {brand_clean}: {e}")
        df["sku"] = ""
        df["asin_master"] = ""
        df["asin_type"] = ""

    # Fallback ASIN from inventory snapshot if sku_master didn't resolve
    asin_col = None
    for cand in ["asin", "ASIN"]:
        if cand in inv_df.columns:
            asin_col = cand; break
    if asin_col is not None:
        model_asin = (
            inv_df[["model", asin_col]]
            .dropna()
            .drop_duplicates(subset="model")
            .rename(columns={asin_col: "asin_inv"})
        )
        model_asin["asin_inv"] = model_asin["asin_inv"].astype(str).str.strip().str.upper()
        df = df.merge(model_asin, on="model", how="left")
    else:
        df["asin_inv"] = ""

    # Prefer master ASIN; fallback to inventory ASIN
    df["asin"] = df["asin_master"].fillna("").astype(str)
    df.loc[df["asin"].isin(["", "NAN"]), "asin"] = df.loc[df["asin"].isin(["", "NAN"]), "asin_inv"].fillna("").astype(str)
    df["sku"] = df["sku"].fillna("").astype(str)
    df["asin_type"] = df.get("asin_type", "").fillna("").astype(str).replace({"nan": "", "NaN": ""})
    df.drop(columns=[c for c in ["asin_master", "asin_inv"] if c in df.columns], inplace=True)

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