"""Pull 1P + 3P returns from the Weekly project's returns ETL.

Operator directive 2026-09-07: "take 1p as well as 3p returns from project
weekly fastapi" — replacing the manually-dropped Additional/returns/*.xlsx
set (last touched 22-27/07, six weeks stale by the time this was wired).
Same pattern as scripts/margin_pull.py (operator directive 2026-09-05).

Source: the Weekly monorepo's returns ETL output
    <weekly repo>/data/processed/returns_snapshot.csv
built by its weekly_app/etl/returns_snapshot.py from the Seller Central
FBA Customer Returns CSVs (3P, ~90-day) + the Vendor Central "1p
Returns.xlsx" retail-analytics export (1P). One row per ASIN with the
split already done: returns_3p, returns_1p, return_units (combined).

Destination (committed input):
    data/input/Additional/returns/returns_snapshot.csv

china_reorder._load_returns_by_asin() prefers this CSV
(returns_90d = return_units) and falls back to the legacy xlsx set only
when it is absent.

Run:  PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/returns_weekly_pull.py
Override source with --source or the WEEKLY_RETURNS_SNAPSHOT env var.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path(
    r"D:\Nitesh\Nitesh Gdrive\Nitesh\Weekly Report - B2B + B2C\FastAPI"
    r"\data\processed\returns_snapshot.csv"
)
DEST = REPO / "data" / "input" / "Additional" / "returns" / "returns_snapshot.csv"

KEEP = [
    "brand", "model", "sku", "asin",
    "return_units", "returns_3p", "returns_1p",
    "sellable_units", "unsellable_units", "sellable_pct",
    "return_pct", "top_reason", "last_return_at",
]
REQUIRED = {"asin", "return_units", "returns_3p", "returns_1p"}

STALE_DAYS = 8  # weekly cadence + a day of grace


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=os.environ.get("WEEKLY_RETURNS_SNAPSHOT",
                                                       str(DEFAULT_SOURCE)))
    args = ap.parse_args()
    src = Path(args.source)

    if not src.exists():
        print(f"FATAL: source not found: {src}")
        return 1

    age_days = (time.time() - src.stat().st_mtime) / 86400
    if age_days > STALE_DAYS:
        print(f"⚠ source is {age_days:.1f} days old — has the weekly returns "
              f"ETL run this week? (weekly_app/etl/returns_snapshot.py)")

    df = pd.read_csv(src)
    df.columns = [str(c).strip() for c in df.columns]
    missing = REQUIRED - set(df.columns)
    if missing:
        print(f"FATAL: source is missing columns {sorted(missing)} — the "
              f"weekly ETL schema changed; update this puller deliberately, "
              f"do not guess.")
        return 1

    out = df[[c for c in KEEP if c in df.columns]].copy()
    out["asin"] = out["asin"].astype(str).str.strip().str.upper()
    out = out[out["asin"] != ""]
    before = len(out)
    out = out.drop_duplicates(subset=["asin"], keep="first")

    DEST.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(DEST, index=False)

    t3 = int(pd.to_numeric(out["returns_3p"], errors="coerce").fillna(0).sum())
    t1 = int(pd.to_numeric(out["returns_1p"], errors="coerce").fillna(0).sum())
    by_brand = out["brand"].value_counts().to_dict() if "brand" in out.columns else {}
    print(f"wrote {len(out)} rows ({before - len(out)} dup-asin dropped) "
          f"-> {DEST.relative_to(REPO)}")
    print(f"  source: {src} (age {age_days:.1f}d)")
    print(f"  totals: 3P {t3} units · 1P {t1} units · combined {t3 + t1}")
    print(f"  brands: {by_brand}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
