"""Pull Pipeline + Open Order from OrderPilot into the AM inventory snapshots.

Operator directive 2026-08-24: "from week 34 onward we will take pipeline and
open orders from orderpilot" — specifically, the numbers that used to come from
the `Pipeline` / `Open Order` channels inside
`data/input/Inventory_snapshot_*.xlsx` now come from OrderPilot's
`import_tracker` table. Every OTHER channel (AMPM, B2B - AMPM, Blinkit, YNT,
1P) is untouched and keeps arriving in the snapshot as before.

WHY IT WRITES BACK INTO THE SNAPSHOT instead of adding a new data source:
the snapshot stays the interface, so no consumer has to change. That matters
because `cb_replenishment.py` reads the Pipeline channel for `china_in_transit`
and the operator directive of 2026-08-18 is "do NOT make any changes in CB
Replenishment". Rewriting the rows in place honours both instructions —
CB Replenishment and China Reorder keep reading exactly what they read today,
they just get OrderPilot's numbers.

Source of truth in OrderPilot:
    import_tracker (one row per sku_id, UNIQUE)
        pipeline_qty    -> Channel "Pipeline"   (in-transit from China)
        open_order_qty  -> Channel "Open Order" (PO placed, not yet shipped)
    joined to sku_master for brand + internal_sku.
See reference_pipeline_vs_open_order_channel.md for the channel semantics —
they were swapped once before, do not re-derive them.

Usage:
    python scripts/orderpilot_imports_pull.py --week 34 --dry-run
    python scripts/orderpilot_imports_pull.py --week 34

Requires ORDERPILOT_DATABASE_URL in .env (OrderPilot runs on a different
database from AM — Neon vs Render — so its own URL is needed; read-only use).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parent.parent

# OrderPilot sku_master.brand -> AM snapshot file. Brands not listed here are
# ignored (Fossil has no import tracker; its in-transit comes from the PO
# tracker instead).
BRAND_FILES: dict[str, str] = {
    "nexlev":         "inventory_snapshot_nexlev.xlsx",
    "audio_array":    "Inventory_snapshot_audio_array.xlsx",
    "white_mulberry": "Inventory_snapshot_WM.xlsx",
    "tonor":          "Inventory_snapshot_tonor.xlsx",
}

# Brand label written into the snapshot's Brand column, matching what the
# existing rows use (services group/filter on these exact strings).
BRAND_LABELS: dict[str, str] = {
    "nexlev":         "Nexlev",
    "audio_array":    "Audio Array",
    "white_mulberry": "White Mulberry",
    "tonor":          "Tonor",
}

PIPELINE_CH = "Pipeline"
OPEN_ORDER_CH = "Open Order"

# The switch starts at W34. Running it against an earlier week would rewrite a
# historical snapshot with today's tracker state, which is not what happened
# that week.
FIRST_VALID_WEEK = 34


def fetch_orderpilot_rows() -> pd.DataFrame:
    url = os.getenv("ORDERPILOT_DATABASE_URL")
    if not url:
        raise SystemExit(
            "❌ ORDERPILOT_DATABASE_URL not set in .env — needed because "
            "OrderPilot is on a different database from AM."
        )
    url = (url.replace("postgresql+psycopg2://", "postgresql://")
              .replace("postgresql+asyncpg://", "postgresql://"))
    sql = """
        SELECT s.brand,
               s.internal_sku          AS sku,
               i.asin,
               i.model_name            AS model,
               COALESCE(i.pipeline_qty, 0)   AS pipeline_qty,
               COALESCE(i.open_order_qty, 0) AS open_order_qty
        FROM import_tracker i
        JOIN sku_master s ON s.id = i.sku_id
    """
    with psycopg2.connect(url) as conn:
        df = pd.read_sql(sql, conn)
    df["brand"] = df["brand"].astype(str).str.strip().str.lower()
    return df


def build_channel_rows(sub: pd.DataFrame, brand_key: str, columns: list[str]) -> pd.DataFrame:
    """Two rows per SKU at most — one Pipeline, one Open Order — skipping
    zeros so the snapshot doesn't fill with empty rows."""
    out = []
    label = BRAND_LABELS.get(brand_key, brand_key)
    for _, r in sub.iterrows():
        for qty, channel in ((r["pipeline_qty"], PIPELINE_CH),
                             (r["open_order_qty"], OPEN_ORDER_CH)):
            q = int(qty or 0)
            if q <= 0:
                continue
            out.append({
                "SKU":     (str(r["sku"]).strip() if pd.notna(r["sku"]) else None),
                "ASIN":    (str(r["asin"]).strip() if pd.notna(r["asin"]) else None),
                "Brand":   label,
                "Model":   (str(r["model"]).strip() if pd.notna(r["model"]) else None),
                "Qty":     q,
                "Channel": channel,
            })
    new = pd.DataFrame(out)
    # Match the snapshot's column order exactly; anything the tracker doesn't
    # carry (category_l0/l1/l2, NLC, Type, Week) stays blank, which is how the
    # existing Pipeline / Open Order rows already look.
    for c in columns:
        if c not in new.columns:
            new[c] = pd.NA
    return new[columns] if len(new) else pd.DataFrame(columns=columns)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True, type=int,
                    help=f"Week number; refuses < {FIRST_VALID_WEEK}")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would change without writing")
    args = ap.parse_args()

    if args.week < FIRST_VALID_WEEK:
        raise SystemExit(
            f"❌ --week {args.week} < {FIRST_VALID_WEEK}. OrderPilot became the "
            f"source from W{FIRST_VALID_WEEK}; earlier weeks keep their original "
            f"snapshot numbers."
        )

    load_dotenv(REPO / ".env")
    op = fetch_orderpilot_rows()
    print(f"OrderPilot import_tracker: {len(op)} rows, "
          f"pipeline={int(op['pipeline_qty'].sum()):,}, "
          f"open_order={int(op['open_order_qty'].sum()):,}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path("C:/Temp/am_snapshot_backup") / stamp
    if not args.dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)

    grand = {"pipe_old": 0, "pipe_new": 0, "oo_old": 0, "oo_new": 0}
    for brand_key, fname in BRAND_FILES.items():
        path = REPO / "data" / "input" / fname
        if not path.exists():
            print(f"  ⚠ {fname}: missing, skipped")
            continue
        df = pd.read_excel(path)
        df.columns = df.columns.astype(str).str.strip()
        if "Channel" not in df.columns:
            print(f"  ⚠ {fname}: no Channel column, skipped")
            continue

        ch = df["Channel"].astype(str).str.strip().str.lower()
        is_target = ch.isin([PIPELINE_CH.lower(), OPEN_ORDER_CH.lower()])
        old_pipe = int(pd.to_numeric(df.loc[ch == PIPELINE_CH.lower(), "Qty"],
                                     errors="coerce").fillna(0).sum())
        old_oo = int(pd.to_numeric(df.loc[ch == OPEN_ORDER_CH.lower(), "Qty"],
                                   errors="coerce").fillna(0).sum())

        sub = op[op["brand"] == brand_key]
        new_rows = build_channel_rows(sub, brand_key, list(df.columns))
        new_pipe = int(pd.to_numeric(
            new_rows.loc[new_rows["Channel"] == PIPELINE_CH, "Qty"],
            errors="coerce").fillna(0).sum()) if len(new_rows) else 0
        new_oo = int(pd.to_numeric(
            new_rows.loc[new_rows["Channel"] == OPEN_ORDER_CH, "Qty"],
            errors="coerce").fillna(0).sum()) if len(new_rows) else 0

        grand["pipe_old"] += old_pipe; grand["pipe_new"] += new_pipe
        grand["oo_old"] += old_oo;     grand["oo_new"] += new_oo

        print(f"  {fname:<36} pipeline {old_pipe:>7,} -> {new_pipe:>7,}   "
              f"open_order {old_oo:>7,} -> {new_oo:>7,}   "
              f"(rows {int(is_target.sum())} -> {len(new_rows)}, "
              f"other channels kept: {int((~is_target).sum())})")

        if args.dry_run:
            continue

        shutil.copy2(path, backup_dir / fname)
        kept = df[~is_target]
        merged = pd.concat([kept, new_rows], ignore_index=True)
        merged.to_excel(path, index=False, sheet_name="Sheet1")

    print()
    print(f"TOTAL pipeline   {grand['pipe_old']:,} -> {grand['pipe_new']:,}")
    print(f"TOTAL open_order {grand['oo_old']:,} -> {grand['oo_new']:,}")
    if args.dry_run:
        print("\n(dry run — nothing written)")
    else:
        print(f"\nbackups: {backup_dir}")


if __name__ == "__main__":
    main()
