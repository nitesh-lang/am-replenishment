"""
Snapshot Fossil SOH weekly for pattern analysis.

Reads current `Fossil Replenishment.xlsx` -> Fossil SOH column, and appends
one row per SKU with snapshot_date, week_iso to a running log at:
    data/input/Fossil Replenishment/fossil_soh_history.csv

Idempotent: if a snapshot for the same date already exists, it is replaced
(safer if the operator re-runs the same day after fresh data).

Usage:
    python scripts/snapshot_fossil_soh.py                      # snapshot today
    python scripts/snapshot_fossil_soh.py --date 2026-06-30    # backdated snapshot
    python scripts/snapshot_fossil_soh.py --from-file path.xlsx --date 2026-06-16
        # snapshot from a specific master file (used by the git-history backfill)
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_MASTER = REPO / "data" / "input" / "Fossil Replenishment" / "Fossil Replenishment.xlsx"
HISTORY = REPO / "data" / "input" / "Fossil Replenishment" / "fossil_soh_history.csv"

COLS = ["snapshot_date", "iso_year", "iso_week", "SKU", "Item No", "Brand",
        "Assortment Type", "Fossil SOH"]


def read_master(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip()
    for c in ("SKU", "Item No", "Brand", "Assortment Type"):
        if c not in df.columns:
            df[c] = ""
    df["Fossil SOH"] = pd.to_numeric(df.get("Fossil SOH"), errors="coerce").fillna(0).astype(int)
    return df[["SKU", "Item No", "Brand", "Assortment Type", "Fossil SOH"]]


def snapshot(master_path: Path, snap_date: date) -> pd.DataFrame:
    df = read_master(master_path)
    df["snapshot_date"] = snap_date.isoformat()
    iso = snap_date.isocalendar()
    df["iso_year"] = iso.year
    df["iso_week"] = iso.week
    return df[COLS]


def append_or_replace(new: pd.DataFrame) -> None:
    if HISTORY.exists():
        old = pd.read_csv(HISTORY)
        old = old[old["snapshot_date"] != new["snapshot_date"].iat[0]]
        combined = pd.concat([old, new], ignore_index=True)
    else:
        combined = new
    combined = combined.sort_values(["snapshot_date", "SKU"]).reset_index(drop=True)
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(HISTORY, index=False)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="Snapshot date YYYY-MM-DD (default: today)")
    ap.add_argument("--from-file", default=None, help="Path to a specific master xlsx (for backfill)")
    args = ap.parse_args()

    snap_date = datetime.fromisoformat(args.date).date() if args.date else date.today()
    master_path = Path(args.from_file) if args.from_file else DEFAULT_MASTER

    snap = snapshot(master_path, snap_date)
    append_or_replace(snap)
    print(f"snapshot {snap_date} -> {len(snap)} rows | history now: {HISTORY.relative_to(REPO)}")


if __name__ == "__main__":
    main()
