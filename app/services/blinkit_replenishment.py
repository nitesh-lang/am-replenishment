import pandas as pd
from pathlib import Path

from app.services.file_cache import get_excel_sheet, get


# Active SKU universe — filter on Expansion Level
ACTIVE_EXPANSION_LEVELS = {"Level 1", "Level 2", "Level 4", "Trial"}

# Channel value in AMPM snapshot files that represents the mother warehouse
AMPM_CHANNEL = "AMPM"

# Source weekly sales file + channel value used by the China Reorder export
BLINKIT_SALES_FILE    = "weekly_sales_snapshot - ChinaReorder.csv"
BLINKIT_SALES_CHANNEL = "Blinkit Sales"

# Default sales window size in weeks (used when from/to not specified)
DEFAULT_SALES_WINDOW_WEEKS = 12


def _load_master() -> pd.DataFrame:
    """Active Blinkit SKU master (35 rows after Expansion Level filter)."""
    df = get_excel_sheet("Blinkit/Input/Nexlev Product Master.xlsx", "Blinkit")
    df = df.copy()
    df["Expansion Level"] = df["Expansion Level"].astype(str).str.strip()
    df = df[df["Expansion Level"].isin(ACTIVE_EXPANSION_LEVELS)]

    keep = [
        "Item ID", "SKU", "ASIN", "EAN", "Brand", "Model",
        "Category L1", "Category L2", "Expansion Level",
        "NLC", "Master Carton", "Blinkit Pricing",
    ]
    keep = [c for c in keep if c in df.columns]
    df = df[keep]

    df = df.rename(columns={
        "Item ID": "item_id",
        "SKU": "sku",
        "ASIN": "asin",
        "EAN": "ean",
        "Brand": "brand",
        "Model": "model",
        "Category L1": "category_l1",
        "Category L2": "category_l2",
        "Expansion Level": "expansion_level",
        "NLC": "nlc",
        "Master Carton": "master_carton",
        "Blinkit Pricing": "blinkit_pricing",
    })

    df["model"] = df["model"].astype(str).str.strip()
    df["brand"] = df["brand"].astype(str).str.strip()
    df["item_id"] = pd.to_numeric(df["item_id"], errors="coerce").astype("Int64")

    # EAN is the 13-digit barcode (a.k.a. Product ID). Keep as a string so it
    # doesn't render in scientific notation on the wire.
    if "ean" in df.columns:
        ean_num = pd.to_numeric(df["ean"], errors="coerce").astype("Int64")
        df["product_id"] = ean_num.astype("string").fillna("")
    else:
        df["product_id"] = ""

    return df


def _load_blinkit_soh() -> pd.DataFrame:
    """Aggregate Blinkit inventory across all 17 warehouses per Item ID.

    SOH per warehouse = Incoming scheduled inventory + Total sellable.
    Returns one row per Item ID with summed SOH.
    """
    df = get_excel_sheet("Blinkit/Inventory/InventoryData.xlsx", "Stock On Hand", header=2)
    df = df.copy()

    required = {"Item ID", "Incoming scheduled inventory", "Total sellable"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"InventoryData.xlsx missing columns: {missing}")

    df["Incoming scheduled inventory"] = pd.to_numeric(df["Incoming scheduled inventory"], errors="coerce").fillna(0)
    df["Total sellable"]               = pd.to_numeric(df["Total sellable"],               errors="coerce").fillna(0)
    df["soh"] = df["Incoming scheduled inventory"] + df["Total sellable"]
    df["Item ID"] = pd.to_numeric(df["Item ID"], errors="coerce").astype("Int64")

    return (
        df.dropna(subset=["Item ID"])
          .groupby("Item ID", as_index=False)["soh"]
          .sum()
          .rename(columns={"Item ID": "item_id", "soh": "blinkit_soh"})
    )


def _load_ampm() -> pd.DataFrame:
    """AMPM mother-warehouse stock per Model, summed across Nexlev + Audio Array brand files.

    Only rows with Channel == 'AMPM' are counted (matches the convention used
    by the other replenishment modules).
    """
    files = [
        "Blinkit/AMPM/inventory_snapshot_nexlev.xlsx",
        "Blinkit/AMPM/Inventory_snapshot_audio_array.xlsx",
    ]
    parts = []
    for f in files:
        try:
            d = get(f)
        except Exception as e:
            print(f"⚠️  AMPM file not loaded ({f}): {e}")
            continue
        d = d.copy()
        if "Channel" in d.columns:
            d = d[d["Channel"].astype(str).str.strip() == AMPM_CHANNEL]
        if "Model" in d.columns and "Qty" in d.columns:
            d["Model"] = d["Model"].astype(str).str.strip()
            d["Qty"]   = pd.to_numeric(d["Qty"], errors="coerce").fillna(0)
            parts.append(d[["Model", "Qty"]])

    if not parts:
        return pd.DataFrame(columns=["model", "ampm_inv"])

    return (
        pd.concat(parts, ignore_index=True)
          .groupby("Model", as_index=False)["Qty"].sum()
          .rename(columns={"Model": "model", "Qty": "ampm_inv"})
    )


def _normalize_week(series: pd.Series) -> pd.Series:
    """Extract integer week number from values like 'Week 12', 'W12', '12'."""
    return (
        series.astype(str)
              .str.extract(r"(\d+)")[0]
              .pipe(pd.to_numeric, errors="coerce")
    )


def get_available_blinkit_weeks() -> list[int]:
    """Distinct week numbers present for channel=Blinkit in weekly_sales_snapshot.

    Returned descending (most recent first), so the frontend can present
    "last N weeks" by default.
    """
    try:
        df = get(BLINKIT_SALES_FILE)
    except Exception:
        return []
    if "channel" not in df.columns or "week" not in df.columns:
        return []
    df = df[df["channel"].astype(str).str.strip() == BLINKIT_SALES_CHANNEL].copy()
    if df.empty:
        return []
    weeks = _normalize_week(df["week"]).dropna().unique().tolist()
    return sorted({int(w) for w in weeks}, reverse=True)


def _load_sales(
    from_week: int | None = None,
    to_week: int | None = None,
) -> tuple[pd.DataFrame, int]:
    """Blinkit sales per SKU within the chosen week range.

    Source: data/input/weekly_sales_snapshot.csv, filtered to channel=Blinkit.
    Defaults to the most recent DEFAULT_SALES_WINDOW_WEEKS weeks if neither
    bound is supplied.

    Returns (df, weeks_in_window) where df has columns [sku, total_sales_window].
    """
    try:
        df = get(BLINKIT_SALES_FILE)
    except Exception as e:
        print(f"⚠️  {BLINKIT_SALES_FILE} not loaded: {e}")
        return pd.DataFrame(columns=["sku", "total_sales_window"]), 0

    if "channel" not in df.columns:
        print(f"⚠️  {BLINKIT_SALES_FILE} has no 'channel' column")
        return pd.DataFrame(columns=["sku", "total_sales_window"]), 0

    df = df[df["channel"].astype(str).str.strip() == BLINKIT_SALES_CHANNEL].copy()

    if df.empty:
        # No Blinkit data in the snapshot yet — return zero with the requested
        # window size (or default) so velocity becomes 0 rather than NaN.
        if from_week is not None and to_week is not None:
            window = max(1, abs(int(to_week) - int(from_week)) + 1)
        else:
            window = DEFAULT_SALES_WINDOW_WEEKS
        return pd.DataFrame(columns=["sku", "total_sales_window"]), window

    df["week_num"] = _normalize_week(df["week"])

    if from_week is not None and to_week is not None:
        lo, hi = sorted([int(from_week), int(to_week)])
        df = df[(df["week_num"] >= lo) & (df["week_num"] <= hi)]
        weeks_in_window = max(1, hi - lo + 1)
    else:
        # Default: most recent DEFAULT_SALES_WINDOW_WEEKS available weeks
        available = sorted(df["week_num"].dropna().unique().tolist(), reverse=True)
        selected = available[:DEFAULT_SALES_WINDOW_WEEKS]
        df = df[df["week_num"].isin(selected)]
        weeks_in_window = max(1, len(selected))

    if "sku" not in df.columns or "units_sold" not in df.columns:
        return pd.DataFrame(columns=["sku", "total_sales_window"]), weeks_in_window

    df["sku"] = df["sku"].astype(str).str.strip()
    df["units_sold"] = pd.to_numeric(df["units_sold"], errors="coerce").fillna(0)

    agg = (
        df.groupby("sku", as_index=False)["units_sold"].sum()
          .rename(columns={"units_sold": "total_sales_window"})
    )
    return agg, weeks_in_window


# ─────────────────────────────────────────────────────────────────────
# STATE-WISE SUPPORT
# ─────────────────────────────────────────────────────────────────────

# Monthly Blinkit order-export files — these are the only source carrying
# Customer State at order grain. The weekly snapshot used by the per-SKU
# view does not have any state column.
BLINKIT_MONTHLY_FILES = [
    ("Blinkit/Sales/March 2026.xlsx", "Sales Report"),
    ("Blinkit/Sales/April 2026.xlsx", "Sales Report"),
    ("Blinkit/Sales/May 2026.xlsx",   "Sales Report"),
]

# Fixed denominator for state-wise avg_weekly_sales (= total_state_sales / 12).
# Independent of the selected sales window — planning convention.
STATEWISE_VELOCITY_DIVISOR = 12

# Map a Blinkit warehouse name to its state by matching the leading city
# token (so "Bengaluru B3", "Bengaluru B4" both -> Karnataka without listing
# every variant). Sorted longest-first to avoid false prefix matches.
_WAREHOUSE_CITY_TO_STATE = {
    "Lucknow":     "Uttar Pradesh",
    "Pune":        "Maharashtra",
    "Bengaluru":   "Karnataka",
    "Kundli":      "Haryana",
    "Mumbai":      "Maharashtra",
    "Nagpur":      "Maharashtra",
    "Surat":       "Gujarat",
    "Noida":       "Uttar Pradesh",
    "Coimbatore":  "Tamil Nadu",
    "Varanasi":    "Uttar Pradesh",
    "Hyderabad":   "Telangana",
    "Chennai":     "Tamil Nadu",
    "Faridabad":   "Haryana",
    "Farukhnagar": "Haryana",
}


def _warehouse_to_state(name: str) -> str | None:
    if not isinstance(name, str):
        return None
    head = name.strip()
    # Try longest-prefix first to avoid 'Lucknow' eating 'LucknowX' etc.
    for city in sorted(_WAREHOUSE_CITY_TO_STATE, key=len, reverse=True):
        if head.lower().startswith(city.lower()):
            return _WAREHOUSE_CITY_TO_STATE[city]
    return None


def _load_blinkit_soh_by_state() -> pd.DataFrame:
    """Per (Item ID, State) SOH summed across the warehouses sitting in that state.

    SOH per warehouse = Incoming scheduled inventory + Total sellable
    (same definition as the per-SKU view; just split by warehouse state).
    """
    df = get_excel_sheet("Blinkit/Inventory/InventoryData.xlsx", "Stock On Hand", header=2)
    df = df.copy()
    df["Item ID"] = pd.to_numeric(df["Item ID"], errors="coerce").astype("Int64")
    df["Incoming scheduled inventory"] = pd.to_numeric(df["Incoming scheduled inventory"], errors="coerce").fillna(0)
    df["Total sellable"]               = pd.to_numeric(df["Total sellable"],               errors="coerce").fillna(0)
    df["soh"] = df["Incoming scheduled inventory"] + df["Total sellable"]

    df["state"] = df["Warehouse Facility Name"].apply(_warehouse_to_state)

    out = (
        df.dropna(subset=["Item ID", "state"])
          .groupby(["Item ID", "state"], as_index=False)["soh"].sum()
          .rename(columns={"Item ID": "item_id", "state": "customer_state", "soh": "state_soh"})
    )
    out["state_soh"] = out["state_soh"].astype(int)
    return out


def _load_monthly_orders(
    from_week: int | None = None,
    to_week: int | None = None,
) -> tuple[pd.DataFrame, int]:
    """Load order-level Blinkit data, filter to DELIVERED, map dates to ISO weeks.

    Returns (df, weeks_in_window). df columns: item_id, customer_state, units, week_num.
    """
    parts = []
    for path, sheet in BLINKIT_MONTHLY_FILES:
        try:
            d = get_excel_sheet(path, sheet)
        except Exception as e:
            print(f"⚠️  Monthly Blinkit file not loaded ({path}): {e}")
            continue
        d = d.copy()
        if "Order Status" in d.columns:
            d = d[d["Order Status"].astype(str).str.strip().str.upper() == "DELIVERED"]
        if not {"Item Id", "Customer State", "Quantity", "Order Date"} <= set(d.columns):
            continue
        d["item_id"]         = pd.to_numeric(d["Item Id"], errors="coerce").astype("Int64")
        d["customer_state"]  = d["Customer State"].astype(str).str.strip()
        d["units"]           = pd.to_numeric(d["Quantity"], errors="coerce").fillna(0)
        d["order_date"]      = pd.to_datetime(d["Order Date"], errors="coerce")
        d["week_num"]        = d["order_date"].dt.isocalendar().week.astype("Int64")
        parts.append(d[["item_id", "customer_state", "units", "week_num"]])

    if not parts:
        return pd.DataFrame(columns=["item_id","customer_state","units","week_num"]), 0

    df = pd.concat(parts, ignore_index=True).dropna(subset=["item_id"])

    # Apply sales window (defaults to most recent DEFAULT_SALES_WINDOW_WEEKS)
    if from_week is not None and to_week is not None:
        lo, hi = sorted([int(from_week), int(to_week)])
        df = df[(df["week_num"] >= lo) & (df["week_num"] <= hi)]
        weeks_in_window = max(1, hi - lo + 1)
    else:
        available = sorted(df["week_num"].dropna().unique().tolist(), reverse=True)
        selected  = available[:DEFAULT_SALES_WINDOW_WEEKS]
        df = df[df["week_num"].isin(selected)]
        weeks_in_window = max(1, len(selected))

    return df, weeks_in_window


def get_available_monthly_weeks() -> list[int]:
    """ISO-week numbers present in the monthly Blinkit order files, desc order."""
    df, _ = _load_monthly_orders(from_week=None, to_week=None)
    if df.empty:
        return []
    weeks = df["week_num"].dropna().unique().tolist()
    return sorted({int(w) for w in weeks}, reverse=True)


def load_blinkit_statewise(
    cover_weeks: int = 8,
    from_week: int | None = None,
    to_week: int | None = None,
) -> tuple[pd.DataFrame, int]:
    """Per-SKU × per-Customer-State replenishment view.

    For each (active SKU, Customer State that bought from it) row:
      state_sales       — units delivered to this state in the window
      state_share_pct   — state_sales / total_sales_for_sku  (display only)
      state_avg_weekly  — state_sales / 12  (fixed denominator — planning
                          convention, independent of the sales window)
      state_required    — state_avg_weekly × cover_weeks
      blinkit_soh       — total SOH across all Blinkit warehouses (per-SKU,
                          shown on every state row of the same SKU for context)
      state_soh         — EXACT sum of SOH across warehouses physically
                          located in that customer state (warehouses are
                          mapped to states by leading city token). States
                          without a local Blinkit warehouse get state_soh=0
      state_deficiency  — max(0, state_required − state_soh)
      ampm_inv          — same shared mother-warehouse pool per SKU
    """
    if cover_weeks <= 0:
        cover_weeks = 8

    master    = _load_master()
    soh_total = _load_blinkit_soh()             # per Item ID — total across warehouses
    soh_state = _load_blinkit_soh_by_state()    # per (Item ID, State) — exact
    ampm      = _load_ampm()                    # per Model
    orders, window = _load_monthly_orders(from_week=from_week, to_week=to_week)

    if orders.empty:
        return pd.DataFrame(), window

    # State sales per (item_id, state)
    state_sales = (
        orders.groupby(["item_id", "customer_state"], as_index=False)["units"].sum()
              .rename(columns={"units": "state_sales"})
    )

    # Total sales per SKU (for share% display only)
    total_by_sku = (
        orders.groupby("item_id", as_index=False)["units"].sum()
              .rename(columns={"units": "total_sales_window"})
    )

    df = state_sales.merge(total_by_sku, on="item_id", how="left")

    # Join master so we get brand/model/sku/etc. + drop inactive SKUs
    df = df.merge(master, on="item_id", how="inner")

    # Total SOH (per item_id) and AMPM (per model) — for context columns
    df = df.merge(soh_total, on="item_id", how="left")
    df = df.merge(ampm,      on="model",   how="left")

    # EXACT state SOH (per item_id × state) — left-join so states without
    # a local warehouse just get NaN -> 0
    df = df.merge(soh_state, on=["item_id", "customer_state"], how="left")

    df["blinkit_soh"]        = df["blinkit_soh"].fillna(0).astype(int)
    df["ampm_inv"]           = df["ampm_inv"].fillna(0).astype(int)
    df["state_sales"]        = df["state_sales"].astype(int)
    df["total_sales_window"] = df["total_sales_window"].astype(int)
    df["state_soh"]          = df["state_soh"].fillna(0).astype(int)

    # Velocity uses a fixed /12 divisor (planning convention)
    df["state_avg_weekly"] = (
        df["state_sales"] / STATEWISE_VELOCITY_DIVISOR
    ).round(0).astype(int)
    df["state_required"]   = (df["state_avg_weekly"] * cover_weeks).astype(int)

    df["state_deficiency"] = (df["state_required"] - df["state_soh"]).clip(lower=0).astype(int)

    # Demand-share % for display (no calculation depends on it)
    df["state_share_pct"] = (
        df["state_sales"] / df["total_sales_window"] * 100
    ).fillna(0).round(1)

    # Sort: brand, then sku, then state by state_sales desc
    df = df.sort_values(
        ["brand", "sku", "state_sales"],
        ascending=[True, True, False],
    ).reset_index(drop=True)

    return df, window


def load_blinkit_replenishment(
    cover_weeks: int = 8,
    from_week: int | None = None,
    to_week: int | None = None,
) -> tuple[pd.DataFrame, int]:
    """Core Blinkit replenishment calc — per-SKU aggregation.

    cover_weeks ∈ {2, 4, 6, 8, 10, 12} — weeks of target cover.
    from_week / to_week — sales window (week numbers). If both omitted,
    defaults to the most recent DEFAULT_SALES_WINDOW_WEEKS weeks.

    Returns (df, weeks_in_window).
    """
    if cover_weeks <= 0:
        cover_weeks = 8

    master = _load_master()
    soh    = _load_blinkit_soh()
    ampm   = _load_ampm()
    sales, window = _load_sales(from_week=from_week, to_week=to_week)

    df = master.merge(soh,   on="item_id", how="left")
    df = df.merge(ampm,      on="model",   how="left")
    df = df.merge(sales,     on="sku",     how="left")

    df["blinkit_soh"]        = df["blinkit_soh"].fillna(0).astype(int)
    df["ampm_inv"]           = df["ampm_inv"].fillna(0).astype(int)
    df["total_sales_window"] = df["total_sales_window"].fillna(0).astype(int)

    df["avg_weekly_sales"] = (df["total_sales_window"] / max(window, 1)).round(0).astype(int)
    df["required_units"]   = (df["avg_weekly_sales"] * cover_weeks).astype(int)
    df["deficiency"]       = (df["required_units"] - df["blinkit_soh"]).clip(lower=0).astype(int)

    # Cap send_qty at AMPM availability — can't ship more than the mother warehouse holds
    df["send_qty"] = df[["deficiency", "ampm_inv"]].min(axis=1).astype(int)

    # Warehouse shortfall = how much AMPM is short of the full deficiency
    df["warehouse_shortfall"] = (df["deficiency"] - df["ampm_inv"]).clip(lower=0).astype(int)

    df["master_carton"] = pd.to_numeric(df.get("master_carton", 0), errors="coerce").fillna(0).astype(int)

    return df, window
