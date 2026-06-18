"""
Data freshness check — per-module input file age.

For each module, declare the input files that drive it + how to compute
each file's "as of" date.  The endpoint returns the per-file age in
weeks relative to the operator's current Sun-Sat working week.

The check is informational, not blocking — the operator occasionally
processes last week's working this week, and the UI banner is
dismissible per (week, module).
"""
from __future__ import annotations

from datetime import date as _date, datetime, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from app.services.week_helper import current_working_week_start, week_label

DATA = Path("data/input")


def _sun_sat_week_number(d: _date) -> int:
    """Sun-Sat week number convention: shift forward 1 day, then ISO week."""
    return (d + timedelta(days=1)).isocalendar().week


def _mtime_date(path: Path) -> _date | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def _snapshot_date_col(path: Path) -> _date | None:
    """First non-empty SnapshotDate value in a CSV (SP-API vendor SOH style)."""
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, usecols=["SnapshotDate"], nrows=5)
        s = df["SnapshotDate"].dropna().astype(str)
        s = s[s != ""]
        if s.empty:
            return None
        return _date.fromisoformat(s.iloc[0].split("T")[0])
    except Exception:
        return None


def _max_week_in_sales(path: Path) -> _date | None:
    """Highest Week N present in weekly_sales_snapshot.csv → Saturday of that week."""
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, usecols=["week"])
        nums = pd.to_numeric(df["week"].astype(str).str.extract(r"(\d+)")[0], errors="coerce").dropna()
        if nums.empty:
            return None
        max_wk = int(nums.max())
        # Convert ISO week → Saturday of that Sun-Sat operator week.
        # Operator's W21 = May 17 (Sun) → May 23 (Sat) 2026.
        # ISO date for (year=2026, week=max_wk, weekday=1)=Mon. Saturday = Mon+5.
        year = datetime.now().year
        try:
            mon = _date.fromisocalendar(year, max_wk, 1)
        except ValueError:
            return None
        # Sun-Sat week ending Saturday = ISO_Mon - 1 day (Sun) + 6 = Saturday before next Sun.
        # Equivalent: ISO Mon of week N + 5 = Saturday of that ISO week, which == Sun-Sat W(N) end.
        return mon + timedelta(days=5)
    except Exception:
        return None


def _latest_fba_sales_week(account_hint: str = "") -> _date | None:
    """Newest Week N folder under data/input/FBA Sales/."""
    root = DATA / "FBA Sales"
    if not root.exists():
        return None
    weeks = []
    for p in root.iterdir():
        if p.is_dir() and p.name.lower().startswith("week"):
            try:
                weeks.append(int(p.name.split()[-1]))
            except (ValueError, IndexError):
                continue
    if not weeks:
        return None
    year = datetime.now().year
    try:
        return _date.fromisocalendar(year, max(weeks), 1) + timedelta(days=5)
    except ValueError:
        return None


# Manifest entry shape:
#   (label, relative_path, "mtime" | "snapshot_col" | "max_sales_week" | "fba_sales_folder")
# Use "max_sales_week" for the per-week weekly_sales_snapshot.csv.
# Use "fba_sales_folder" for the FBA Sales/Week N folder family (no path).
ModuleSpec = list[tuple[str, str, str]]

# Only weekly-refreshed *data* inputs belong here. Master sheets (e.g.
# CB Replenishment Master, sku_master, brand replenishment masters) are
# updated on an ad-hoc cadence (monthly or less) and would generate
# noise if flagged each week — they're intentionally excluded.
MODULES: dict[str, ModuleSpec] = {
    "replenishment": [
        ("Weekly Sales Snapshot",       "weekly_sales_snapshot.csv",             "max_sales_week"),
        ("Nexlev Inventory Snapshot",   "inventory_snapshot_nexlev.xlsx",        "mtime"),
        ("Nexlev Amazon Inventory",     "inventory_amazon_nexlev.csv",           "mtime"),
        ("Nexlev Ledger",               "inventory_ledger_nexlev.csv",           "mtime"),
        ("Viomi Amazon Inventory",      "inventory_amazon_viomi.csv",            "mtime"),
        ("AA Inventory Snapshot",       "Inventory_snapshot_audio_array.xlsx",   "mtime"),
        ("AA Amazon Inventory",         "inventory_amazon_audio_array.csv",      "mtime"),
        ("WM Inventory Snapshot",       "Inventory_snapshot_WM.xlsx",            "mtime"),
        ("WM Amazon Inventory",         "inventory_amazon_WM.csv",               "mtime"),
    ],
    "cb-replenishment": [
        ("Weekly Sales Snapshot",       "weekly_sales_snapshot.csv",             "max_sales_week"),
        ("AA Inventory Snapshot",       "Inventory_snapshot_audio_array.xlsx",   "mtime"),
        ("Tonor Inventory Snapshot",    "Inventory_snapshot_tonor.xlsx",         "mtime"),
        ("CB SOH (SP-API, AA)",         "vendor_soh_audio_array.csv",            "snapshot_col"),
        ("CB SOH (SP-API, Tonor)",      "vendor_soh_tonor.csv",                  "snapshot_col"),
        ("In-Transit PO (manual)",      "In_Transit_PO data.xlsx",               "mtime"),
    ],
    "wm-replenishment": [
        ("Weekly Sales Snapshot",       "weekly_sales_snapshot.csv",             "max_sales_week"),
        ("WM Inventory Snapshot",       "Inventory_snapshot_WM.xlsx",            "mtime"),
        ("WM In-Transit PO (manual)",   "In_Transit_PO data - WM.xlsx",          "mtime"),
    ],
    "china-reorder": [
        ("Weekly Sales Snapshot",       "weekly_sales_snapshot.csv",             "max_sales_week"),
        ("AA Inventory Snapshot",       "Inventory_snapshot_audio_array.xlsx",   "mtime"),
        ("Tonor Inventory Snapshot",    "Inventory_snapshot_tonor.xlsx",         "mtime"),
        ("WM Inventory Snapshot",       "Inventory_snapshot_WM.xlsx",            "mtime"),
        ("Nexlev Inventory Snapshot",   "inventory_snapshot_nexlev.xlsx",        "mtime"),
    ],
    "fc-allocation": [
        ("FBA Sales (latest week)",     "",                                       "fba_sales_folder"),
        ("Nexlev Inbound (SP-API)",     "inbound_shipments_nexlev.csv",          "mtime"),
        ("Nexlev Ledger",               "inventory_ledger_nexlev.csv",           "mtime"),
        ("AA Ledger",                   "inventory_ledger_Audio Array.csv",      "mtime"),
        ("WM Ledger",                   "inventory_ledger_WM.csv",               "mtime"),
        ("Viomi Ledger",                "inventory_ledger_viomi.csv",            "mtime"),
    ],
    "fossil-replenishment": [
        # Fossil SOH file (Fossil - SOH.xlsx) is redundant — ledger + in-transit
        # cover the same surface. Master sheet is updated ad-hoc, not weekly.
        ("Fossil In-Transit/Open PO",   "Fossil Replenishment/In-Transit_Open_PO_Fossil.xlsx","mtime"),
        ("Fossil Ledger",               "Fossil Replenishment/inventory_ledger_fossil.csv",  "mtime"),
        ("FBA Sales (latest week)",     "",                                                    "fba_sales_folder"),
    ],
    "blinkit-replenishment": [
        ("Blinkit Replenishment Input", "Blinkit/Input/Replenishment_8-06-2026.xlsx",        "mtime"),
        ("Blinkit Sales (June 2026)",   "Blinkit/Sales/June 2026.xlsx",                      "mtime"),
    ],
    "fba-inbound": [
        ("Nexlev Inbound (SP-API)",     "inbound_shipments_nexlev.csv",          "mtime"),
    ],
}


def _as_of(path_rel: str, kind: str) -> _date | None:
    if kind == "fba_sales_folder":
        return _latest_fba_sales_week()
    path = DATA / path_rel
    if kind == "mtime":
        return _mtime_date(path)
    if kind == "snapshot_col":
        return _snapshot_date_col(path)
    if kind == "max_sales_week":
        return _max_week_in_sales(path)
    return None


def check_module(module: str) -> dict:
    spec = MODULES.get(module, [])
    ws = current_working_week_start()                    # Sunday of current working week
    we = ws + timedelta(days=6)                          # Saturday
    current_week_num = _sun_sat_week_number(we)

    files = []
    any_stale = False
    fresh = 0
    stale = 0
    for label, path_rel, kind in spec:
        as_of = _as_of(path_rel, kind)
        if as_of is None:
            files.append({
                "label":           label,
                "path":            path_rel or "(FBA Sales folder)",
                "as_of":           None,
                "as_of_week":      None,
                "fresh":           False,
                "missing":         True,
                "stale_by_weeks":  None,
                "source":          kind,
            })
            any_stale = True
            stale += 1
            continue

        # File is "fresh" iff as_of >= current week's Sunday OR as_of >= week_label end
        is_fresh = as_of >= ws
        delta_days = (ws - as_of).days
        stale_weeks = max(0, (delta_days + 6) // 7) if not is_fresh else 0
        files.append({
            "label":          label,
            "path":           path_rel or "(FBA Sales folder)",
            "as_of":          as_of.isoformat(),
            "as_of_week":     _sun_sat_week_number(as_of),
            "fresh":          is_fresh,
            "missing":        False,
            "stale_by_weeks": stale_weeks,
            "source":         kind,
        })
        if is_fresh:
            fresh += 1
        else:
            any_stale = True
            stale += 1

    return {
        "module":            module,
        "current_week":      {
            "num":   current_week_num,
            "start": ws.isoformat(),
            "end":   we.isoformat(),
            "label": week_label(ws),
        },
        "files":             files,
        "any_stale":         any_stale,
        "fresh_count":       fresh,
        "stale_count":       stale,
    }
