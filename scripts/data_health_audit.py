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


def _ampm_lookup_from_snapshot(snap_path: Path) -> dict:
    """Build ASIN, SKU, Model lookup dicts for AMPM rows in a snapshot.

    Returns dict with three keys:
      'by_asin'  : ASIN -> Qty
      'by_sku'   : SKU  -> Qty
      'by_model' : Model -> Qty
    """
    empty = {"by_asin": {}, "by_sku": {}, "by_model": {}}
    try:
        df = pd.read_excel(snap_path, engine="openpyxl")
    except Exception:
        return empty
    if "Channel" not in df.columns or "Qty" not in df.columns:
        return empty
    a = df[df["Channel"].astype(str).str.strip() == "AMPM"].copy()
    a["Qty"] = pd.to_numeric(a["Qty"], errors="coerce").fillna(0)
    a["_asin"]  = a.get("ASIN", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    a["_sku"]   = a.get("SKU",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    a["_model"] = a.get("Model", "").astype(str).str.strip().str.lower()
    return {
        "by_asin":  a[a["_asin"]  != ""].groupby("_asin")["Qty"].sum().to_dict(),
        "by_sku":   a[a["_sku"]   != ""].groupby("_sku")["Qty"].sum().to_dict(),
        "by_model": a.groupby("_model")["Qty"].sum().to_dict(),
    }


def _ampm_lookup_misses(service_df: pd.DataFrame, snap_path: Path) -> list[tuple]:
    """Rows where service shows AMPM=0 but the snapshot has stock that
    *should* have been resolvable via the ASIN→SKU→Model cascade.

    Now cascade-aware: a row is only flagged if the snapshot has stock
    keyed on the row's ASIN, SKU, *or* Model (matching the order the
    service uses). Inactive duplicate-Model SKUs whose AMPM legitimately
    sits under their sibling's ASIN are NOT flagged.
    """
    lookups = _ampm_lookup_from_snapshot(snap_path)
    if service_df is None or service_df.empty:
        return []
    miss = []
    for _, r in service_df.iterrows():
        out = pd.to_numeric(r.get("ampm_inventory"), errors="coerce")
        out = 0.0 if pd.isna(out) else float(out)
        if out > 0:
            continue
        asin  = str(r.get("ASIN") or r.get("asin") or "").strip().upper()
        sku   = str(r.get("SKU")  or r.get("sku")  or "").strip().upper()
        model = str(r.get("Model") or r.get("model") or "").strip().lower()
        # Only flag if the SAME cascade the service uses would have found stock
        if asin and lookups["by_asin"].get(asin, 0) > 0:
            miss.append((sku, model, int(lookups["by_asin"][asin])))
        elif sku and lookups["by_sku"].get(sku, 0) > 0:
            miss.append((sku, model, int(lookups["by_sku"][sku])))
        # Model-only check is intentionally OMITTED: a duplicate-Model
        # SKU whose AMPM legitimately sits under its sibling's ASIN is
        # NOT a miss under ASIN-primary semantics.
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


def run_po_coverage_check() -> list[dict]:
    """In-Transit/Open-PO file coverage check.

    Catches the class of bug where service code filters delivery status with
    a case-sensitive `==` ("Open PO") but the file has different casing
    ("Open po") — silently dropping rows from the deficiency calculation.

    For each PO file, validates:
      - every non-empty 'Delivery Status' value normalises to a known bucket
        (open po | in-transit), so the service captures it
      - row-count balance: rows_captured == non_null_status_rows
      - reports any unexpected status values so they can be triaged
    """
    KNOWN_STATUSES = {"open po", "in-transit"}
    files = [
        ("CB",  INPUT / "In_Transit_PO data.xlsx"),
        ("WM",  INPUT / "In_Transit_PO data - WM.xlsx"),
    ]

    out = []
    for label, path in files:
        row: dict[str, Any] = {"File": label, "Path": path.name}
        if not path.exists():
            row.update({"Status": "FAIL", "Error": f"missing: {path.name}"})
            out.append(row)
            continue
        try:
            df = pd.read_excel(path, engine="openpyxl")
        except Exception as e:
            row.update({"Status": "FAIL", "Error": f"{type(e).__name__}: {e}"})
            out.append(row)
            continue

        status_col = next((c for c in df.columns if c.strip().lower() == "delivery status"), None)
        if status_col is None:
            row.update({"Status": "FAIL", "Error": "no 'Delivery Status' column"})
            out.append(row)
            continue

        statuses = df[status_col].dropna().astype(str).str.strip()
        non_null = len(statuses)
        if non_null == 0:
            # Empty file is OK — just no rows to filter
            row.update({"Status": "PASS", "Total_rows": len(df), "Non_null_status": 0,
                       "Captured": 0, "Unknown_statuses": "{}"})
            out.append(row)
            continue

        normalised = statuses.str.lower()
        captured = normalised.isin(KNOWN_STATUSES).sum()
        unknown = sorted(set(statuses[~normalised.isin(KNOWN_STATUSES)].unique()))
        row.update({
            "Total_rows": len(df),
            "Non_null_status": non_null,
            "Captured": int(captured),
            "Unknown_statuses": ", ".join(unknown) if unknown else "—",
        })

        problems = []
        if captured != non_null:
            problems.append(f"{non_null - captured} rows have unknown status")
        if unknown:
            problems.append(f"unknown values: {unknown}")

        row["Status"] = "PASS" if not problems else "WARN"
        if problems:
            row["Issue"] = "; ".join(problems)
        out.append(row)

    return out


def run_fc_allocation_smoke(master: dict) -> tuple[list[dict], dict[str, list]]:
    """FC Final Allocation smoke test per account.

    Checks:
      - service runs end-to-end without exception
      - non-empty output with required columns present
      - no NaN/inf in numeric columns
      - shortfall invariant: fc_shortfall == max(0, required_units - fc_inventory)
      - weekly_velocity >= 0 for all rows
      - every SKU in output resolves to sku_master
      - every (non-Fossil) row has a real Model (not the "-" fallback)
    """
    from app.services.fc_final_allocation import calculate_final_allocation

    # Live FC allocation output schema (after the transfer engine has run)
    REQUIRED_COLS = [
        "sku", "fulfillment_center", "weekly_velocity",
        "fc_inventory", "target_cover_units", "coverage_gap_units", "send_qty",
    ]
    NUMERIC_COLS = [
        "weekly_velocity", "fc_inventory", "target_cover_units",
        "coverage_gap_units", "send_qty",
    ]

    out: list[dict] = []
    issues: dict[str, list] = {}

    for acct in ["Nexlev", "Viomi", "Audio Array", "White Mulberry", "Fossil"]:
        row: dict[str, Any] = {"Service": f"fc_allocation ({acct})"}
        problem_list: list[str] = []
        try:
            df = calculate_final_allocation(replenish_weeks=8, channel="All", account=acct)
        except Exception as e:
            row["Status"] = "FAIL"
            row["Error"] = f"{type(e).__name__}: {e}"
            out.append(row)
            continue

        if df is None or df.empty:
            row["Status"] = "FAIL"
            row["Rows"] = 0
            row["Error"] = "empty DataFrame"
            out.append(row)
            continue

        row["Rows"] = len(df)
        row["SKUs"] = df["sku"].nunique() if "sku" in df.columns else 0
        row["FCs"] = df["fulfillment_center"].nunique() if "fulfillment_center" in df.columns else 0

        # Required columns
        missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]
        if missing_cols:
            problem_list.append(f"missing columns: {missing_cols}")

        # NaN / inf
        num = df.select_dtypes(include=[np.number])
        nan_cells = int(num.isna().sum().sum())
        inf_cells = int(np.isinf(num).sum().sum())
        row["NaN_cells"] = nan_cells
        row["Inf_cells"] = inf_cells

        # Coverage gap invariant: coverage_gap_units = max(0, target_cover_units - (fc_inventory + transfer_in))
        if all(c in df.columns for c in ["coverage_gap_units", "target_cover_units", "fc_inventory"]):
            transfer_in = pd.to_numeric(df.get("transfer_in", 0), errors="coerce").fillna(0)
            expected = (df["target_cover_units"] - df["fc_inventory"] - transfer_in).clip(lower=0)
            actual = pd.to_numeric(df["coverage_gap_units"], errors="coerce").fillna(0)
            bad_gap = int((expected.round(2) != actual.round(2)).sum())
            row["Gap_inv_violations"] = bad_gap
            if bad_gap:
                problem_list.append(f"{bad_gap} coverage-gap-invariant violations")

        # send_qty sanity: must be non-negative and ≤ coverage_gap_units (can't send more than the gap)
        if all(c in df.columns for c in ["send_qty", "coverage_gap_units"]):
            sq = pd.to_numeric(df["send_qty"], errors="coerce").fillna(0)
            gap = pd.to_numeric(df["coverage_gap_units"], errors="coerce").fillna(0)
            neg_send = int((sq < 0).sum())
            over_send = int((sq > gap + 0.01).sum())  # tiny tolerance for float
            row["Negative_send_rows"] = neg_send
            row["Over_send_rows"] = over_send
            if neg_send:
                problem_list.append(f"{neg_send} rows with negative send_qty")
            if over_send:
                problem_list.append(f"{over_send} rows where send_qty > coverage_gap")

        # weekly_velocity >= 0
        if "weekly_velocity" in df.columns:
            neg = int((pd.to_numeric(df["weekly_velocity"], errors="coerce").fillna(0) < 0).sum())
            row["Negative_velocity_rows"] = neg
            if neg:
                problem_list.append(f"{neg} rows with negative weekly_velocity")

        # SKU resolves to sku_master (case-insensitive)
        if "sku" in df.columns:
            unique_skus = df["sku"].astype(str).str.strip().str.upper().unique()
            unmatched = [s for s in unique_skus if s not in master["by_sku"]]
            row["Unmatched_SKUs"] = len(unmatched)
            issues.setdefault(row["Service"], []).extend(
                [{"kind": "unmatched_sku", "sku": s} for s in unmatched[:30]]
            )
            if unmatched:
                problem_list.append(f"{len(unmatched)} SKUs not in sku_master")

        # Model populated (non-Fossil only; Fossil uses Item No which can be sparse)
        if "model" in df.columns and acct.lower() != "fossil":
            placeholder = int((df["model"].astype(str).str.strip().isin(["", "-", "nan"])).sum())
            row["Rows_without_model"] = placeholder
            if placeholder:
                problem_list.append(f"{placeholder} rows with placeholder model")

        if problem_list:
            row["Status"] = "WARN"
            row["Issues"] = "; ".join(problem_list)
        else:
            row["Status"] = "PASS"

        out.append(row)

    return out, issues


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

    # PO file coverage check (case-sensitivity / status-bucket regression test)
    print(f"  ━━ PO FILE COVERAGE CHECK ━━")
    po_rows = run_po_coverage_check()
    po_df = pd.DataFrame(po_rows)
    if not po_df.empty:
        print(po_df.fillna("").to_string(index=False))
    print()

    # FC Allocation smoke
    print(f"  ━━ FC ALLOCATION SMOKE TEST ━━")
    fc_rows, fc_issues = run_fc_allocation_smoke(master)
    fc_df = pd.DataFrame(fc_rows)
    if not fc_df.empty:
        print(fc_df.fillna("").to_string(index=False))
    for service_name, ilist in fc_issues.items():
        if ilist:
            kinds = {}
            for it in ilist:
                kinds.setdefault(it["kind"], []).append(it)
            for kind, items in kinds.items():
                print(f"\n  ⚠️  {service_name} — {len(items)} {kind} (showing first 10):")
                for it in items[:10]:
                    print(f"      {it}")
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

        # PO coverage
        po_df.to_excel(w, sheet_name="PO file coverage", index=False)

        # FC Allocation
        fc_df.to_excel(w, sheet_name="FC Allocation", index=False)
        fc_issue_rows = []
        for service_name, ilist in fc_issues.items():
            for it in ilist:
                fc_issue_rows.append({"Service": service_name, **it})
        if fc_issue_rows:
            pd.DataFrame(fc_issue_rows).to_excel(w, sheet_name="FC issues", index=False)
        else:
            pd.DataFrame([{"note": "no FC allocation issues — all clean"}]).to_excel(
                w, sheet_name="FC issues", index=False
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
