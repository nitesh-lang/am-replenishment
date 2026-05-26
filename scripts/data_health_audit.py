"""Per-account data-health audit for the replenishment pipeline.

Run after every weekly data refresh:
    python scripts/data_health_audit.py

For each brand (Audio Array, WM, CB, Nexlev, Viomi, Fossil), checks:
  - Required input files exist and are non-empty
  - Replenishment master SKU/Model align with sku_master
  - Inventory snapshot has AMPM channel rows
  - Amazon FBA inventory file loaded, has positive qty
  - Inventory ledger recent dates present
  - Replenishment service runs end-to-end without NaN/inf
  - AMPM model coverage % across the master

Writes a timestamped Excel report to D:/Nitesh/Normalization/ and prints
a pass/fail checklist to stdout. Designed to be re-run weekly.
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

REPO = Path(__file__).resolve().parent.parent
INPUT = REPO / "data" / "input"
NORM = Path(r"D:/Nitesh/Normalization")
MASTER_PATH = Path(
    r"G:/Other computers/My Laptop/D/Nitesh/Weekly Report - B2B + B2C/FastAPI/data/master/sku_master.xlsx"
)

# Add repo to sys.path so we can import services
sys.path.insert(0, str(REPO))


def _ok(b: bool) -> str:
    return "PASS" if b else "FAIL"


def _read(path: Path, sheet: str | int | None = None, **kw) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, **kw)
    # Default to first sheet (0) if not specified — passing None returns a dict
    return pd.read_excel(path, sheet_name=sheet if sheet is not None else 0, engine="openpyxl", **kw)


def _load_master() -> dict:
    df = pd.read_excel(MASTER_PATH, engine="openpyxl")
    df["_sku"] = df["FBA SKU"].astype(str).str.strip().str.upper()
    df["_model"] = df["Model"].astype(str).str.strip().str.lower()
    return {
        "rows": len(df),
        "by_sku": df.drop_duplicates("_sku").set_index("_sku")[["Model", "_model"]].to_dict("index"),
        "model_set": set(df["_model"].dropna()) - {"", "nan"},
    }


# ─────────────────────────────────────────────────────────────────────
# Per-account spec — declarative
# ─────────────────────────────────────────────────────────────────────
ACCOUNTS = [
    {
        "name": "Audio Array",
        "repl":       ("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "AA"),
        "inv_snap":   "Inventory_snapshot_audio_array.xlsx",
        "amz_inv":    "inventory_amazon_audio_array.csv",
        "ledger":     "inventory_ledger_Audio Array.csv",
        "shipments":  "fba_shipments_Audio Array.csv",
    },
    {
        "name": "WM",
        "repl":       ("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "WM"),
        "inv_snap":   "Inventory_snapshot_WM.xlsx",
        "amz_inv":    "inventory_amazon_WM.csv",
        "ledger":     "inventory_ledger_WM.csv",
        "shipments":  "fba_shipments_WM.csv",
    },
    {
        "name": "CB",
        "repl":       ("CB Replenishment_Master.xlsx", "Sheet1"),
        "inv_snap":   None,  # CB uses the AA snapshot
        "amz_inv":    None,
        "ledger":     None,
        "shipments":  None,
    },
    {
        "name": "Nexlev",
        "repl":       ("replenishment_master_nexlev.xlsx", "nexlev"),
        "inv_snap":   "inventory_snapshot_nexlev.xlsx",
        "amz_inv":    "inventory_amazon_nexlev.csv",
        "ledger":     "inventory_ledger_nexlev.csv",
        "shipments":  "fba_shipments_nexlev.csv",
    },
    {
        "name": "Viomi",
        "repl":       ("replenishment_master_viomi.xlsx", "Viomi"),
        "inv_snap":   "inventory_snapshot_nexlev.xlsx",  # Viomi shares Nexlev snapshot
        "amz_inv":    "inventory_amazon_viomi.csv",
        "ledger":     "inventory_ledger_viomi.csv",
        "shipments":  "fba_shipments_viomi.csv",
    },
    {
        "name": "Fossil",
        "repl":       ("Fossil Replenishment/Fossil Replenishment.xlsx", None),
        "inv_snap":   "Fossil Replenishment/Fossil - SOH.xlsx",
        "amz_inv":    None,
        "ledger":     "Fossil Replenishment/inventory_ledger_fossil.csv",
        "shipments":  "Fossil Replenishment/fba_shipments_fossil.csv",
    },
]


def check_account(acct: dict, master: dict) -> dict:
    """Run all checks for one account. Returns a dict of check → (status, detail)."""
    r: dict[str, Any] = {"_account": acct["name"]}

    # ─── 1. Files exist and are non-empty ──────────────────────────────
    for label, key in [("repl_file", "repl"), ("inv_snap_file", "inv_snap"),
                       ("amz_inv_file", "amz_inv"), ("ledger_file", "ledger"),
                       ("shipments_file", "shipments")]:
        v = acct[key]
        if v is None:
            r[label] = ("SKIP", "n/a")
            continue
        f = INPUT / (v[0] if isinstance(v, tuple) else v)
        if not f.exists():
            r[label] = ("FAIL", f"missing: {f.name}")
        elif f.stat().st_size == 0:
            r[label] = ("FAIL", f"empty: {f.name}")
        else:
            r[label] = ("PASS", f"{f.stat().st_size:,} bytes")

    # ─── 2. Replenishment master sanity ───────────────────────────────
    try:
        f, sheet = acct["repl"]
        repl = _read(INPUT / f, sheet=sheet)
        repl = repl.dropna(subset=["SKU"] if "SKU" in repl.columns else [repl.columns[0]])
        sku_col = "SKU" if "SKU" in repl.columns else next((c for c in repl.columns if "sku" in c.lower()), None)
        mod_col = "Model" if "Model" in repl.columns else next((c for c in repl.columns if "model" in c.lower()), None)

        if not sku_col:
            r["repl_columns"] = ("FAIL", f"missing SKU column (have: {list(repl.columns)[:5]})")
            r["repl_rows"] = ("FAIL", "could not parse")
            r["sku_in_master"] = ("FAIL", "skipped — no SKU col")
            r["model_in_master"] = ("SKIP", "no Model column in this schema")
        elif not mod_col:
            # Fossil-style schema: SKU present, Model absent. Skip model checks.
            r["repl_columns"] = ("PASS", f"SKU={sku_col} (no Model column — schema variant)")
            r["repl_rows"] = ("PASS", str(len(repl)))
            dups = repl[sku_col].astype(str).str.strip().str.upper().duplicated(keep=False).sum()
            r["repl_no_dupes"] = ("PASS", "no duplicate SKUs") if dups == 0 else ("WARN", f"{dups} duplicate SKU rows")
            sku_set = repl[sku_col].astype(str).str.strip().str.upper()
            unmatched = [s for s in sku_set if s not in master["by_sku"]]
            r["sku_in_master"] = ("PASS" if not unmatched else "WARN", f"{len(unmatched)} unmatched")
            r["_unmatched_skus"] = unmatched[:50]
            r["model_in_master"] = ("SKIP", "no Model column in this schema")
        else:
            r["repl_columns"] = ("PASS", f"SKU={sku_col}, Model={mod_col}")
            r["repl_rows"] = ("PASS", str(len(repl)))

            # Dupes
            dups = repl[sku_col].astype(str).str.strip().str.upper().duplicated(keep=False).sum()
            r["repl_no_dupes"] = ("PASS", "no duplicate SKUs") if dups == 0 else ("WARN", f"{dups} duplicate SKU rows")

            # vs sku_master
            repl["_sku"] = repl[sku_col].astype(str).str.strip().str.upper()
            repl["_mod"] = repl[mod_col].astype(str).str.strip().str.lower()
            unmatched = [(s, m) for s, m in zip(repl["_sku"], repl["_mod"]) if s not in master["by_sku"]]
            model_mm = [
                (s, repl_m, master["by_sku"][s]["Model"])
                for s, repl_m in zip(repl["_sku"], repl["_mod"])
                if s in master["by_sku"] and master["by_sku"][s]["_model"] != repl_m
            ]
            r["sku_in_master"] = ("PASS" if not unmatched else "FAIL", f"{len(unmatched)} unmatched")
            r["model_in_master"] = ("PASS" if not model_mm else "FAIL", f"{len(model_mm)} mismatches")
            r["_unmatched_skus"] = unmatched[:50]
            r["_model_mismatches"] = model_mm[:50]
    except Exception as e:
        r["repl_rows"] = ("FAIL", f"{type(e).__name__}: {e}")
        r["sku_in_master"] = ("FAIL", "skipped — load failed")
        r["model_in_master"] = ("FAIL", "skipped — load failed")

    # ─── 3. Inventory snapshot — AMPM coverage ────────────────────────
    if acct["inv_snap"]:
        try:
            snap = _read(INPUT / acct["inv_snap"])
            r["inv_snap_rows"] = ("PASS", str(len(snap)))
            if "Channel" not in snap.columns:
                # Some brands (e.g., Fossil) ship a single-channel SOH file with no Channel column
                r["inv_snap_channels"] = ("SKIP", "no Channel column — single-channel SOH")
                r["inv_ampm_rows"] = ("SKIP", "n/a — single-channel SOH")
            else:
                channels = snap["Channel"].dropna().astype(str).str.strip().unique()
                r["inv_snap_channels"] = ("PASS", f"{len(channels)} channels: {sorted(channels)[:6]}")
                ampm = snap[snap["Channel"].astype(str).str.strip() == "AMPM"]
                r["inv_ampm_rows"] = ("PASS" if len(ampm) > 0 else "FAIL", f"{len(ampm)} AMPM rows")

                # AMPM model coverage vs replenishment master
                if "Model" in ampm.columns and "_mod" in repl.columns:
                    ampm_set = set(ampm["Model"].astype(str).str.strip().str.lower())
                    missing = sorted(set(repl["_mod"]) - ampm_set - {""})
                    pct = (1 - len(missing) / max(1, len(set(repl["_mod"])))) * 100
                    r["ampm_model_coverage"] = (
                        "PASS" if pct >= 50 else "WARN",
                        f"{pct:.0f}% of master models have AMPM rows ({len(missing)} missing)"
                    )
                    r["_ampm_missing_models"] = missing[:50]
        except Exception as e:
            r["inv_snap_rows"] = ("FAIL", f"{type(e).__name__}: {e}")

    # ─── 4. Amazon FBA inventory ──────────────────────────────────────
    if acct["amz_inv"]:
        try:
            amz = _read(INPUT / acct["amz_inv"])
            r["amz_inv_rows"] = ("PASS", str(len(amz)))
            for col in ["sku", "asin", "afn-total-quantity"]:
                if col not in amz.columns:
                    r[f"amz_col_{col}"] = ("FAIL", f"missing column: {col}")
                    break
            else:
                r["amz_inv_columns"] = ("PASS", "sku/asin/afn-total-quantity present")
                total = pd.to_numeric(amz["afn-total-quantity"], errors="coerce").fillna(0).sum()
                pos = int((pd.to_numeric(amz["afn-total-quantity"], errors="coerce").fillna(0) > 0).sum())
                r["amz_inv_positive_skus"] = (
                    "PASS" if pos > 0 else "WARN",
                    f"{pos} SKUs with stock, total qty = {int(total)}"
                )
        except Exception as e:
            r["amz_inv_rows"] = ("FAIL", f"{type(e).__name__}: {e}")

    # ─── 5. Inventory ledger — recent dates ──────────────────────────
    if acct["ledger"]:
        try:
            led = _read(INPUT / acct["ledger"])
            r["ledger_rows"] = ("PASS", str(len(led)))
            date_col = next((c for c in led.columns if "date" in c.lower()), None)
            if date_col:
                dates = pd.to_datetime(led[date_col], errors="coerce")
                most_recent = dates.max()
                age_days = (datetime.now() - most_recent).days if pd.notna(most_recent) else 999
                r["ledger_recent"] = (
                    "PASS" if age_days <= 14 else "WARN",
                    f"most recent {most_recent.date() if pd.notna(most_recent) else 'NaT'} ({age_days}d ago)"
                )
        except Exception as e:
            r["ledger_rows"] = ("FAIL", f"{type(e).__name__}: {e}")

    # ─── 6. FBA shipments file present ────────────────────────────────
    if acct["shipments"]:
        try:
            ship = _read(INPUT / acct["shipments"])
            r["shipments_rows"] = ("PASS", str(len(ship)))
        except Exception as e:
            r["shipments_rows"] = ("FAIL", f"{type(e).__name__}: {e}")

    return r


def _ampm_lookup_from_snapshot(snap_path: Path) -> dict[str, float]:
    """Build a case-insensitive Model -> total AMPM Qty dict from a snapshot file."""
    try:
        df = pd.read_excel(snap_path, engine="openpyxl")
    except Exception:
        return {}
    if "Channel" not in df.columns or "Model" not in df.columns or "Qty" not in df.columns:
        return {}
    a = df[df["Channel"].astype(str).str.strip() == "AMPM"].copy()
    a["Model"] = a["Model"].astype(str).str.strip()
    a["Qty"] = pd.to_numeric(a["Qty"], errors="coerce").fillna(0)
    return {k.strip().lower(): float(v) for k, v in a.groupby("Model")["Qty"].sum().to_dict().items()}


def _ampm_lookup_misses(service_df: pd.DataFrame, snap_path: Path) -> list[tuple]:
    """Models where service output shows AMPM=0 but the snapshot has stock.
    Returns list of (SKU, Model, snapshot_qty)."""
    ampm = _ampm_lookup_from_snapshot(snap_path)
    if not ampm or service_df is None or service_df.empty:
        return []
    miss = []
    for _, r in service_df.iterrows():
        model = str(r.get("Model") or r.get("model") or "").strip()
        out = pd.to_numeric(r.get("ampm_inventory"), errors="coerce")
        out = 0.0 if pd.isna(out) else float(out)
        if out == 0 and model:
            k = model.lower()
            if k in ampm and ampm[k] > 0:
                miss.append((r.get("SKU") or r.get("sku"), model, int(ampm[k])))
    return miss


def run_services_smoke():
    """End-to-end service smoke test — does each replenishment service
    return non-empty output with no NaN/inf, and is AMPM correctly populated
    for every model that has stock in the snapshot?"""
    from app.services.file_cache import preload
    preload()

    out = []

    snapshot_by_acct = {
        "NEXLEV":          INPUT / "inventory_snapshot_nexlev.xlsx",
        "VIOMI":           INPUT / "inventory_snapshot_nexlev.xlsx",
        "AUDIO ARRAY":     INPUT / "Inventory_snapshot_audio_array.xlsx",
        "WHITE MULBERRY":  INPUT / "Inventory_snapshot_WM.xlsx",
    }

    from app.services.replenishment import calculate_replenishment
    for acct in ["NEXLEV", "VIOMI", "AUDIO ARRAY", "WHITE MULBERRY"]:
        try:
            df = calculate_replenishment(sales_window=12, replenish_weeks=8, account=acct)
            num = df.select_dtypes(include=[np.number])
            misses = _ampm_lookup_misses(df, snapshot_by_acct[acct])
            status = "WARN" if misses else "PASS"
            out.append({
                "Service": f"replenishment ({acct})",
                "Status": status,
                "Rows": len(df),
                "NaN_cells": int(num.isna().sum().sum()),
                "Inf_cells": int(np.isinf(num).sum().sum()),
                "AMPM_pop": int((df.get("ampm_inventory", pd.Series([0])) > 0).sum()),
                "AMPM_lookup_misses": len(misses),
                "_misses": misses[:30],
            })
        except Exception as e:
            out.append({"Service": f"replenishment ({acct})", "Status": "FAIL", "Error": f"{type(e).__name__}: {e}"})

    # Blinkit
    try:
        from app.services.blinkit_replenishment import load_blinkit_replenishment, load_blinkit_statewise
        sku_df, _ = load_blinkit_replenishment(cover_weeks=8)
        st_df, _ = load_blinkit_statewise(cover_weeks=8)
        out.append({
            "Service": "blinkit_per_sku",
            "Status": "PASS",
            "Rows": len(sku_df),
            "NaN_cells": int(sku_df.select_dtypes(include=[np.number]).isna().sum().sum()),
            "AMPM_pop": int((sku_df.get("ampm_inv", pd.Series([0])) > 0).sum()),
        })
        out.append({
            "Service": "blinkit_per_state",
            "Status": "PASS",
            "Rows": len(st_df),
            "NaN_cells": int(st_df.select_dtypes(include=[np.number]).isna().sum().sum()),
        })
    except Exception as e:
        out.append({"Service": "blinkit", "Status": "FAIL", "Error": f"{type(e).__name__}: {e}"})

    return out


def main():
    print(f"\n{'=' * 78}\n  DATA HEALTH AUDIT — {datetime.now():%Y-%m-%d %H:%M}\n{'=' * 78}\n")

    master = _load_master()
    print(f"  sku_master loaded: {master['rows']} rows, {len(master['model_set'])} unique Models\n")

    results = [check_account(a, master) for a in ACCOUNTS]

    # Pretty per-account checklist
    for r in results:
        name = r.get("_account", "?")
        print(f"  ━━ {name} ━━")
        for key, val in r.items():
            if key.startswith("_") or key == "_account":
                continue
            status, detail = val if isinstance(val, tuple) else (val, "")
            mark = {"PASS": "✓", "FAIL": "✗", "WARN": "!", "SKIP": "-"}.get(status, "?")
            print(f"    [{mark}] {status:5}  {key:28} {detail}")
        # Print first few unmatched / mismatched rows if any
        if r.get("_unmatched_skus"):
            print(f"        unmatched SKUs: {r['_unmatched_skus'][:5]}")
        if r.get("_model_mismatches"):
            print(f"        model mismatches: {r['_model_mismatches'][:5]}")
        print()

    # Service smoke test
    print(f"  ━━ SERVICE SMOKE TEST ━━")
    svc = run_services_smoke()
    # Keep _misses out of the printed/written table but surface them below
    misses_by_service = {row["Service"]: row.pop("_misses", []) for row in svc}
    svc_df = pd.DataFrame(svc)
    print(svc_df.fillna("").to_string(index=False))

    # Flag any AMPM lookup misses with detail
    for name, m in misses_by_service.items():
        if m:
            print(f"\n  ⚠️  {name} — {len(m)} models with AMPM=0 in service but stock in snapshot:")
            for sku, model, qty in m[:10]:
                print(f"      SKU={sku}  Model={model}  snapshot_qty={qty}")
            if len(m) > 10:
                print(f"      ... +{len(m) - 10} more")
    print()

    # ─── Excel report ─────────────────────────────────────────────────
    NORM.mkdir(parents=True, exist_ok=True)
    out_path = NORM / f"data_health_audit_{datetime.now():%Y%m%d_%H%M}.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        summary_rows = []
        for r in results:
            name = r.get("_account") or "?"
            checks = {k: v for k, v in r.items() if not k.startswith("_")}
            row = {"Account": name}
            for k, v in checks.items():
                status = v[0] if isinstance(v, tuple) else v
                row[k] = status
            summary_rows.append(row)
        pd.DataFrame(summary_rows).to_excel(w, sheet_name="Summary", index=False)

        # Detail rows per account
        for r in results:
            name = (r.get("_account") or "?").replace("/", "_")[:25]
            rows = []
            for k, v in r.items():
                if k.startswith("_"):
                    continue
                status, detail = v if isinstance(v, tuple) else (v, "")
                rows.append({"Check": k, "Status": status, "Detail": detail})
            pd.DataFrame(rows).to_excel(w, sheet_name=name, index=False)

        svc_df.to_excel(w, sheet_name="Services", index=False)
        # Detail sheet listing every AMPM lookup miss (if any)
        miss_rows = []
        for name, m in misses_by_service.items():
            for sku, model, qty in m:
                miss_rows.append({"Service": name, "SKU": sku, "Model": model, "AMPM_qty_in_snapshot": qty})
        if miss_rows:
            pd.DataFrame(miss_rows).to_excel(w, sheet_name="AMPM lookup misses", index=False)
        else:
            pd.DataFrame([{"note": "no AMPM lookup misses — all clean"}]).to_excel(
                w, sheet_name="AMPM lookup misses", index=False
            )

    print(f"  Report written: {out_path}")

    # Exit code: non-zero if any FAIL
    has_fail = any(
        (v[0] if isinstance(v, tuple) else v) == "FAIL"
        for r in results for k, v in r.items() if not k.startswith("_")
    )
    sys.exit(1 if has_fail else 0)


if __name__ == "__main__":
    main()
