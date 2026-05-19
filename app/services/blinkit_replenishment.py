import pandas as pd
from pathlib import Path

from app.services.file_cache import get_excel_sheet, get


# Active SKU universe — filter on Expansion Level
ACTIVE_EXPANSION_LEVELS = {"Level 1", "Level 2", "Level 4", "Trial"}

# Channel value in AMPM snapshot files that represents the mother warehouse
AMPM_CHANNEL = "AMPM"

# Approx weeks in the 3-month sales window we ship today
SALES_WINDOW_WEEKS = 13


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


def _load_sales_3m() -> pd.DataFrame:
    """Total Blinkit sales units per Item Id across the 3-month window."""
    months = ["March 2026.xlsx", "April 2026.xlsx", "May 2026.xlsx"]
    parts = []
    for m in months:
        try:
            d = get_excel_sheet(f"Blinkit/Sales/{m}", "Sales Report")
        except Exception as e:
            print(f"⚠️  Sales file not loaded ({m}): {e}")
            continue
        d = d.copy()
        if "Item Id" not in d.columns or "Quantity" not in d.columns:
            continue
        d["Item Id"]  = pd.to_numeric(d["Item Id"],  errors="coerce").astype("Int64")
        d["Quantity"] = pd.to_numeric(d["Quantity"], errors="coerce").fillna(0)
        parts.append(d[["Item Id", "Quantity"]])

    if not parts:
        return pd.DataFrame(columns=["item_id", "total_sales_3m"])

    return (
        pd.concat(parts, ignore_index=True)
          .dropna(subset=["Item Id"])
          .groupby("Item Id", as_index=False)["Quantity"].sum()
          .rename(columns={"Item Id": "item_id", "Quantity": "total_sales_3m"})
    )


def load_blinkit_replenishment(cover_weeks: int = 8) -> pd.DataFrame:
    """Core Blinkit replenishment calc — per-SKU aggregation.

    cover_weeks ∈ {2, 4, 6, 8, 10, 12} — weeks of target cover.
    """
    if cover_weeks <= 0:
        cover_weeks = 8

    master = _load_master()
    soh    = _load_blinkit_soh()
    ampm   = _load_ampm()
    sales  = _load_sales_3m()

    df = master.merge(soh,   on="item_id", how="left")
    df = df.merge(ampm,      on="model",   how="left")
    df = df.merge(sales,     on="item_id", how="left")

    df["blinkit_soh"]    = df["blinkit_soh"].fillna(0).astype(int)
    df["ampm_inv"]       = df["ampm_inv"].fillna(0).astype(int)
    df["total_sales_3m"] = df["total_sales_3m"].fillna(0).astype(int)

    df["avg_weekly_sales"] = (df["total_sales_3m"] / SALES_WINDOW_WEEKS).round(0).astype(int)
    df["required_units"]   = (df["avg_weekly_sales"] * cover_weeks).astype(int)
    df["deficiency"]       = (df["required_units"] - df["blinkit_soh"]).clip(lower=0).astype(int)

    # Cap send_qty at AMPM availability — can't ship more than the mother warehouse holds
    df["send_qty"] = df[["deficiency", "ampm_inv"]].min(axis=1).astype(int)

    # Warehouse shortfall = how much AMPM is short of the full deficiency
    df["warehouse_shortfall"] = (df["deficiency"] - df["ampm_inv"]).clip(lower=0).astype(int)

    df["master_carton"] = pd.to_numeric(df.get("master_carton", 0), errors="coerce").fillna(0).astype(int)

    return df
