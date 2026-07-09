"""ONE-OFF (W27 exception): override AMPM Qty in inventory_snapshot files
using 'AMPM Qty Updated' from the operator's week-27 tracking sheet.

Match cascade: ASIN → SKU → Model (per master_alignment_hierarchy rule).

Behavior:
  - For each brand snapshot, replace the Qty of every Channel=AMPM row
    whose SKU/ASIN/Model matches an entry in the AMPM tracker file.
  - New SKUs (present in tracker, missing in snapshot) are ADDED as AMPM
    channel rows so downstream services see them.
  - Rows in the snapshot with no tracker match are left untouched.

Snapshots updated:
  data/input/inventory_snapshot_nexlev.xlsx  (Nexlev + Viomi both read this)
  data/input/Inventory_snapshot_audio_array.xlsx
  data/input/Inventory_snapshot_WM.xlsx
  data/input/Inventory_snapshot_tonor.xlsx

Not committed automatically — operator commits after eyeball.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
INPUT = REPO / "data" / "input"
AMPM_FILE = INPUT / "AMPM inventory and Other Inventories - Week 27.xlsx"

BRAND_TO_SNAPSHOT = {
    "Nexlev":         "inventory_snapshot_nexlev.xlsx",
    "Audio Array":    "Inventory_snapshot_audio_array.xlsx",
    "White Mulberry": "Inventory_snapshot_WM.xlsx",
    "Tonor":          "Inventory_snapshot_tonor.xlsx",
}


def _norm(v) -> str:
    if pd.isna(v):
        return ""
    return str(v).strip().upper()


def load_ampm_updates() -> pd.DataFrame:
    df = pd.read_excel(AMPM_FILE, sheet_name="AMPM Inventory")
    df.columns = df.columns.str.strip()
    df["Brand"] = df["Brand"].astype(str).str.strip()
    df["SKU"]   = df["SKU"].astype(str).str.strip().str.upper()
    df["Asin"]  = df["Asin"].astype(str).str.strip().str.upper()
    df["Model Name"] = df["Model Name"].astype(str).str.strip()
    df["updated_qty"] = pd.to_numeric(df["AMPM Qty Updated"], errors="coerce").fillna(0).astype(int)
    # Normalize brand aliases (trailing space, casing)
    df["Brand"] = df["Brand"].replace({"Nexlev ": "Nexlev", "audio Array": "Audio Array"})
    return df[["Brand", "SKU", "Asin", "Model Name", "updated_qty"]]


def apply_override(brand: str, tracker: pd.DataFrame) -> None:
    snap_path = INPUT / BRAND_TO_SNAPSHOT[brand]
    if not snap_path.exists():
        print(f"  ! snapshot missing for {brand}: {snap_path}")
        return

    snap = pd.read_excel(snap_path)
    snap.columns = snap.columns.str.strip()

    brand_rows = tracker[tracker["Brand"].str.lower() == brand.lower()].copy()
    if brand_rows.empty:
        print(f"  ! {brand}: no rows in tracker, skipping")
        return

    # Build lookup dicts for the cascade
    by_asin  = dict(zip(brand_rows["Asin"],       brand_rows["updated_qty"]))
    by_sku   = dict(zip(brand_rows["SKU"],        brand_rows["updated_qty"]))
    by_model = dict(zip(brand_rows["Model Name"].str.upper(), brand_rows["updated_qty"]))

    # Also normalize snapshot side
    snap["_asin"]  = snap["ASIN"].apply(_norm)
    snap["_sku"]   = snap["SKU"].apply(_norm)
    snap["_model"] = snap["Model"].apply(_norm) if "Model" in snap.columns else ""
    snap["_channel"] = snap["Channel"].astype(str).str.strip()

    ampm_mask = snap["_channel"].str.upper() == "AMPM"
    n_ampm_before = int(ampm_mask.sum())
    old_sum = int(snap.loc[ampm_mask, "Qty"].fillna(0).sum())

    updated_asins_used, updated_skus_used, updated_models_used = set(), set(), set()
    updates_applied = 0

    for idx, row in snap[ampm_mask].iterrows():
        new_qty = None
        if row["_asin"] and row["_asin"] in by_asin:
            new_qty = by_asin[row["_asin"]]
            updated_asins_used.add(row["_asin"])
        elif row["_sku"] and row["_sku"] in by_sku:
            new_qty = by_sku[row["_sku"]]
            updated_skus_used.add(row["_sku"])
        elif row["_model"] and row["_model"] in by_model:
            new_qty = by_model[row["_model"]]
            updated_models_used.add(row["_model"])
        if new_qty is not None:
            snap.at[idx, "Qty"] = int(new_qty)
            updates_applied += 1

    # New rows — tracker entries whose SKU/ASIN/Model didn't match ANY existing AMPM row
    used_keys = set()
    for _, row in snap[ampm_mask].iterrows():
        used_keys.update((row["_asin"], row["_sku"], row["_model"]))
    new_rows = []
    for _, r in brand_rows.iterrows():
        a = r["Asin"] or ""
        s = r["SKU"] or ""
        m = (r["Model Name"] or "").upper()
        if a not in used_keys and s not in used_keys and m not in used_keys:
            new_rows.append({
                "SKU": r["SKU"],
                "ASIN": r["Asin"],
                "Brand": r["Brand"],
                "Model": r["Model Name"],
                "Qty": int(r["updated_qty"]),
                "Channel": "AMPM",
            })
    if new_rows:
        add_df = pd.DataFrame(new_rows)
        # Match column set to existing snapshot
        for c in snap.columns:
            if c not in add_df.columns and not c.startswith("_"):
                add_df[c] = ""
        add_df = add_df[[c for c in snap.columns if not c.startswith("_")]]
        snap_out = pd.concat([snap.drop(columns=[c for c in snap.columns if c.startswith("_")]),
                              add_df], ignore_index=True)
    else:
        snap_out = snap.drop(columns=[c for c in snap.columns if c.startswith("_")])

    # Write back
    snap_out.to_excel(snap_path, index=False)
    new_ampm = int((snap_out["Channel"].astype(str).str.strip().str.upper() == "AMPM").sum())
    new_sum  = int(snap_out.loc[snap_out["Channel"].astype(str).str.strip().str.upper() == "AMPM", "Qty"].fillna(0).sum())
    print(f"  {brand:16s} AMPM rows: {n_ampm_before} -> {new_ampm} (+{len(new_rows)} new)")
    print(f"    AMPM Qty sum: {old_sum} -> {new_sum}")
    print(f"    Match sources: {len(updated_asins_used)} ASIN + {len(updated_skus_used)} SKU + {len(updated_models_used)} Model = {updates_applied} overrides")


def main() -> None:
    print(f"Reading tracker: {AMPM_FILE.name}")
    tracker = load_ampm_updates()
    print(f"  {len(tracker)} tracker rows, total updated_qty = {tracker['updated_qty'].sum()}")
    print()
    for brand in BRAND_TO_SNAPSHOT:
        apply_override(brand, tracker)


if __name__ == "__main__":
    main()
