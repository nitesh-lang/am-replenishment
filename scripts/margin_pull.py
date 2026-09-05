"""Pull margin numbers from the Weekly project's margin tool.

Operator directive 2026-09-05: "from now onwards please pull margin numbers
directly from margin tool which is under weekly project" — replacing the
manually-dropped Additional/margin/*.xlsx files (last touched 22/07, i.e.
six weeks stale by the time this was wired).

Source: the Weekly monorepo's margin ETL output
    <weekly repo>/data/processed/margin_snapshot.csv
which weekly_app/etl/margin_snapshot.py rebuilds from the operator's
per-brand "Margin Data" sheets each weekly run. It is the SAME upstream
data the old xlsx drops came from, one hop earlier and always current.

Destination (committed like every other input):
    data/input/Additional/margin/margin_snapshot.csv

china_reorder._load_margin_by_asin() prefers this CSV and falls back to
the legacy xlsx files only when it is absent, so an un-run puller degrades
to the old behaviour instead of blanking margins.

Run:  PYTHONIOENCODING=utf-8 venv/Scripts/python.exe scripts/margin_pull.py
Override source with --source or the WEEKLY_MARGIN_SNAPSHOT env var.
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
    r"\data\processed\margin_snapshot.csv"
)
DEST = REPO / "data" / "input" / "Additional" / "margin" / "margin_snapshot.csv"

# Columns the AM side consumes now or plausibly next; everything else in the
# weekly snapshot (stock fields etc.) is dropped — AM has its own stock truth.
KEEP = [
    "brand", "sku", "asin", "model",
    "nlc", "gross_margin", "gross_margin_pct",
    "net_margin", "net_margin_pct",
]
REQUIRED = {"asin", "net_margin", "net_margin_pct"}

STALE_DAYS = 8  # weekly cadence + 1 day of grace


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=os.environ.get("WEEKLY_MARGIN_SNAPSHOT",
                                                       str(DEFAULT_SOURCE)))
    args = ap.parse_args()
    src = Path(args.source)

    if not src.exists():
        print(f"FATAL: source not found: {src}")
        return 1

    age_days = (time.time() - src.stat().st_mtime) / 86400
    if age_days > STALE_DAYS:
        # Warn loudly but still pull — a week-old margin beats a July xlsx.
        print(f"⚠ source is {age_days:.1f} days old — has the weekly margin "
              f"ETL run this week? (weekly_app/etl/margin_snapshot.py)")

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

    by_brand = out["brand"].value_counts().to_dict() if "brand" in out.columns else {}
    print(f"wrote {len(out)} rows ({before - len(out)} dup-asin dropped) "
          f"-> {DEST.relative_to(REPO)}")
    print(f"  source: {src} (age {age_days:.1f}d)")
    print(f"  brands: {by_brand}")
    n_missing_margin = int(out["net_margin_pct"].isna().sum())
    if n_missing_margin:
        print(f"  note: {n_missing_margin} rows carry blank net_margin_pct "
              f"(present upstream too — not a pull defect)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
