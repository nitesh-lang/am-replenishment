"""
Enrich Inventory_snapshot_*.xlsx Model column using sku_master.

Rule (per operator): ASIN-first → SKU fallback → existing Model fallback.
- Reads sku_master.xlsx, builds ASIN→Model and SKU→Model maps.
- For each snapshot file, fills blank/NaN Model with the master lookup.
- Reports per-channel before/after coverage.

Usage:
    python scripts/enrich_snapshot_model.py --dry-run   # report only, no writes
    python scripts/enrich_snapshot_model.py             # writes back in-place
"""
from __future__ import annotations
import argparse
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
INPUT = REPO / "data" / "input"

SNAPSHOTS = [
    "inventory_snapshot_nexlev.xlsx",
    "Inventory_snapshot_audio_array.xlsx",
    "Inventory_snapshot_WM.xlsx",
    "Inventory_snapshot_tonor.xlsx",
]


def load_master_maps() -> tuple[dict[str, str], dict[str, str]]:
    sm = pd.read_excel(INPUT / "sku_master.xlsx")
    sm.columns = sm.columns.str.strip()
    sm["_asin"]  = sm["ASIN"].astype(str).str.strip().str.upper()
    sm["_sku"]   = sm["FBA SKU"].astype(str).str.strip().str.upper()
    sm["_model"] = sm["Model"].astype(str).str.strip()

    asin_to_model = (
        sm[(sm["_asin"] != "") & (sm["_asin"] != "NAN") & (sm["_model"] != "")]
          .drop_duplicates(subset=["_asin"], keep="first")
          .set_index("_asin")["_model"].to_dict()
    )
    sku_to_model = (
        sm[(sm["_sku"] != "") & (sm["_sku"] != "NAN") & (sm["_sku"] != "0") & (sm["_model"] != "")]
          .drop_duplicates(subset=["_sku"], keep="first")
          .set_index("_sku")["_model"].to_dict()
    )
    return asin_to_model, sku_to_model


def enrich_one(path: Path, asin_to_model: dict[str, str],
               sku_to_model: dict[str, str], dry_run: bool) -> None:
    df = pd.read_excel(path)
    if "Model" not in df.columns:
        print(f"  ! {path.name}: no Model column, skipping")
        return

    df["Model"] = df["Model"].astype("object")
    before = df["Model"].notna().sum()
    blank_mask = df["Model"].isna() | (df["Model"].astype(str).str.strip() == "")

    asin_key = df["ASIN"].astype(str).str.strip().str.upper()
    sku_key  = df["SKU"].astype(str).str.strip().str.upper()

    via_asin = asin_key.map(asin_to_model)
    via_sku  = sku_key.map(sku_to_model)

    filled = via_asin.where(via_asin.notna(), via_sku)
    df.loc[blank_mask, "Model"] = filled[blank_mask]

    after = df["Model"].notna().sum()
    still_blank = df["Model"].isna() | (df["Model"].astype(str).str.strip() == "")

    print(f"  {path.name}: {len(df)} rows, Model populated {before} -> {after}")
    if still_blank.sum() > 0:
        unresolved = df[still_blank][["SKU", "ASIN", "Channel"]].head(8)
        print(f"    {still_blank.sum()} rows still missing Model. First few:")
        for _, r in unresolved.iterrows():
            print(f"      SKU={r['SKU']} ASIN={r['ASIN']} Channel={r['Channel']}")

    if not dry_run and after > before:
        df.to_excel(path, index=False)
        print(f"    -> wrote {path.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    asin_to_model, sku_to_model = load_master_maps()
    print(f"sku_master maps: {len(asin_to_model)} ASIN, {len(sku_to_model)} SKU")
    print(f"mode: {'DRY RUN' if args.dry_run else 'WRITE BACK'}\n")

    for fn in SNAPSHOTS:
        path = INPUT / fn
        if not path.exists():
            print(f"  ! {fn} not found, skipping")
            continue
        enrich_one(path, asin_to_model, sku_to_model, args.dry_run)


if __name__ == "__main__":
    main()
