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

def get_excel_sheet(filename: str, sheet_name: str, header: int = 0) -> pd.DataFrame:
    """Get a specific sheet from an Excel file.

    header — row index (0-based) to use as the column header. Pass a non-zero
    value when the source file has banner / grouped header rows above the
    real column names.
    """
    key = f"{filename}::{sheet_name}::h{header}"
    if key not in _cache:
        path = DATA_PATH / filename
        _cache[key] = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl", header=header)
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
        "sku_master.xlsx",
        "Inventory_snapshot_audio_array.xlsx",
        "Inventory_snapshot_tonor.xlsx",
        "In_Transit_PO data.xlsx",
        "In_Transit_PO data - WM.xlsx",
        "weekly_sales_snapshot.csv",
        "Inventory_snapshot_WM.xlsx",
        "inventory_snapshot_nexlev.xlsx",
        "replenishment_master_nexlev.xlsx",
        "replenishment_master_viomi.xlsx",
        "inventory_amazon_nexlev.csv",
        "inventory_amazon_viomi.csv",
        "inventory_amazon_audio_array.csv",
        "inventory_amazon_WM.csv",
        "inbound_shipments_nexlev.csv",
        "inventory_ledger_nexlev.csv",
        "inventory_ledger_viomi.csv",
        "inventory_ledger_WM.csv",
        "inventory_ledger_Audio Array.csv",
        "Fossil Replenishment/Fossil Replenishment.xlsx",
        "Fossil Replenishment/Fossil - SOH.xlsx",
        "Fossil Replenishment/inventory_ledger_fossil.csv",
        "Fossil Replenishment/In-Transit_Open_PO_Fossil.xlsx",
        # Blinkit AMPM snapshots
        "Blinkit/AMPM/inventory_snapshot_nexlev.xlsx",
        "Blinkit/AMPM/Inventory_snapshot_audio_array.xlsx",
        # Reorder Intelligence — additional data (reviews + returns)
        "Additional/reviews/Audio Array.csv",
        "Additional/reviews/Nexlev.csv",
        "Additional/reviews/Tonor.csv",
        "Additional/reviews/White Mulberry.csv",
        "Additional/returns/Audio Array FBA Returns.csv",
        "Additional/returns/Nexlev.csv",
        "Additional/returns/CRPL.csv",
        "Additional/returns/viomi.csv",
    ]

    # Excel files with specific sheets
    sheet_files = [
        ("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "AA", 0),
        ("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "WM", 0),
        ("replenishment_master_nexlev.xlsx", "nexlev", 0),
        ("replenishment_master_viomi.xlsx",  "Viomi",  0),
        # Blinkit module
        ("Blinkit/Input/Nexlev Product Master.xlsx", "Blinkit", 0),
        ("Blinkit/Inventory/InventoryData.xlsx", "Stock On Hand", 2),
        # Monthly order exports — used by the state-wise Blinkit view
        ("Blinkit/Sales/March 2026.xlsx", "Sales Report", 0),
        ("Blinkit/Sales/April 2026.xlsx", "Sales Report", 0),
        ("Blinkit/Sales/May 2026.xlsx",   "Sales Report", 0),
        # Blinkit Bulk RO — per-warehouse acceptance caps (Max Inventory etc.)
        ("Blinkit/RO/SELLER_BULK_SHIPMENT_INPUT.xlsx", "Bulk RO", 0),
        # Reorder Intelligence — margin sheets (one per brand)
        ("Additional/margin/Audio Array.xlsx",    "Margin Data", 0),
        ("Additional/margin/Nexlev.xlsx",         "Margin Data", 0),
        ("Additional/margin/White Mulberry.xlsx", "Margin Data", 0),
    ]

    # Load sheet files first
    for entry in sheet_files:
        # Support legacy 2-tuple entries too
        if len(entry) == 2:
            f, sheet = entry; header = 0
        else:
            f, sheet, header = entry
        try:
            get_excel_sheet(f, sheet, header=header)
        except Exception as e:
            print(f"⚠️ Could not preload {f}::{sheet}: {e}")

    # Load plain files
    for f in files:
        try:
            get(f)
        except Exception as e:
            print(f"⚠️ Could not preload {f}: {e}")