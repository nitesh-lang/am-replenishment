import pandas as pd
from pathlib import Path

DATA_PATH = Path("data/input")

_cache = {}

def get(filename: str) -> pd.DataFrame:
    """Get a file from cache, loading it if not present."""
    if filename not in _cache:
        path = DATA_PATH / filename
        if filename.endswith(".csv"):
            _cache[filename] = pd.read_csv(path)
        else:
            _cache[filename] = pd.read_excel(path, engine="openpyxl")
        print(f"📂 Loaded into cache: {filename}")
    return _cache[filename].copy()

def get_excel_sheet(filename: str, sheet_name: str) -> pd.DataFrame:
    """Get a specific sheet from an Excel file."""
    key = f"{filename}::{sheet_name}"
    if key not in _cache:
        path = DATA_PATH / filename
        _cache[key] = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
        print(f"📂 Loaded into cache: {key}")
    return _cache[key].copy()

def invalidate(filename: str = None):
    """Clear cache for a file or all files."""
    if filename:
        keys = [k for k in _cache if k.startswith(filename)]
        for k in keys:
            del _cache[k]
    else:
        _cache.clear()
    print(f"🗑️ Cache cleared: {filename or 'ALL'}")

def preload():
    """Preload all known data files at startup."""

    # Plain files (CSV + Excel)
    files = [
        "CB Replenishment_Master.xlsx",
        "weekly_sales_snapshot - CB Replenishment.csv",
        "Inventory_snapshot_audio_array.xlsx",
        "Inventory_snapshot_tonor.xlsx",
        "In_Transit_PO data.xlsx",
        "In_Transit_PO data - WM.xlsx",
        "weekly_sales_snapshot.csv",
        "weekly_sales_snapshot - ChinaReorder.csv",
        "Inventory_snapshot_WM.xlsx",
        "inventory_snapshot_nexlev.xlsx",
        "replenishment_master_nexlev.xlsx",
        "replenishment_master_viomi.xlsx",
        "inventory_amazon_nexlev.csv",
        "inventory_amazon_viomi.csv",
        "inventory_amazon_audio_array.csv",
        "inventory_amazon_WM.csv",
        "fba_shipments_nexlev.csv",
        "fba_shipments_viomi.csv",
        "fba_shipments_WM.csv",
        "fba_shipments_Audio Array.csv",
        "inventory_ledger_nexlev.csv",
        "inventory_ledger_viomi.csv",
        "inventory_ledger_WM.csv",
        "inventory_ledger_Audio Array.csv",
        "Fossil Replenishment/Fossil Replenishment.xlsx",
        "Fossil Replenishment/Fossil - SOH.xlsx",
        "Fossil Replenishment/fba_shipments_fossil.csv",
        "Fossil Replenishment/inventory_ledger_fossil.csv",
        "Fossil Replenishment/In-Transit_Open_PO_Fossil.xlsx",
    ]

    # Excel files with specific sheets
    sheet_files = [
        ("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "AA"),
        ("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "WM"),
        ("replenishment_master_nexlev.xlsx", "Nexlev"),
        ("replenishment_master_viomi.xlsx", "Viomi"),
    ]

    # Load sheet files first
    for f, sheet in sheet_files:
        try:
            get_excel_sheet(f, sheet)
        except Exception as e:
            print(f"⚠️ Could not preload {f}::{sheet}: {e}")

    # Load plain files
    for f in files:
        try:
            get(f)
        except Exception as e:
            print(f"⚠️ Could not preload {f}: {e}")