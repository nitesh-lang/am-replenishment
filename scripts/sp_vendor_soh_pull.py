"""
SP-API Vendor SOH Pull (1P / Vendor Central)
============================================

Pulls sellable on-hand inventory per ASIN from the Vendor Inventory Report and
writes one CSV per brand, matching the `channel == "1p"` slice schema used in
data/input/Inventory_snapshot_<brand>.xlsx.

Accounts:
    AUDIOARRAY      -> Cambium Retail Pvt Ltd (Mumbai - cb) vendor account.
                      Sells BOTH Audio Array + Tonor brands; split via sku_master.
                      Feeds CB Replenishment.
    WHITEMULBERRY   -> Clicktech vendor account for White Mulberry brand.
                      Feeds Clicktech Replenishment.

Outputs:
    data/input/vendor_soh_audio_array.csv
    data/input/vendor_soh_tonor.csv
    data/input/vendor_soh_wm.csv

Schema (matches 1p rows in Inventory_snapshot_<brand>.xlsx):
    SKU, ASIN, Brand, Model, category_l0, category_l1, category_l2,
    NLC, Qty, Channel, Type, Week
    + extra SP-API columns: OpenPOUnits, Aged90PlusUnits, UnsellableUnits,
                            SellableCost, SnapshotDate

Required env vars (.env):
    SP_API_VENDOR_REFRESH_TOKEN_AUDIOARRAY
    SP_API_VENDOR_REFRESH_TOKEN_WHITEMULBERRY
    SP_LWA_CLIENT_ID_AUDIOARRAY      (AdPilot LWA app)
    SP_LWA_CLIENT_SECRET_AUDIOARRAY
    SP_LWA_CLIENT_ID_WHITEMULBERRY
    SP_LWA_CLIENT_SECRET_WHITEMULBERRY

Usage:
    python scripts/sp_vendor_soh_pull.py                  # both accounts
    python scripts/sp_vendor_soh_pull.py --account AUDIOARRAY
    python scripts/sp_vendor_soh_pull.py --account WHITEMULBERRY
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass
print = functools.partial(print, flush=True)

LWA_URL    = "https://api.amazon.com/auth/o2/token"
SPAPI_HOST = "https://sellingpartnerapi-eu.amazon.com"
MARKETPLACE_ID = "A21TJRUUN4KGV"
REPO_ROOT  = Path(__file__).resolve().parent.parent

# Account -> output file slugs + brand split rule.
# Two SEPARATE Amazon logins, two separate vendor authorizations:
#   info@cambium-retail → cb vendor (AA + Tonor) + Nexlev seller
#   kanwal@cambium-retail.com → CRPL vendor (WMI-DRPL etc, holds WM 1P)
ACCOUNTS = {
    "AUDIOARRAY": {
        "outputs": {
            "Audio Array": REPO_ROOT / "data" / "input" / "vendor_soh_audio_array.csv",
            "Tonor":       REPO_ROOT / "data" / "input" / "vendor_soh_tonor.csv",
        },
    },
    "WHITEMULBERRY": {
        "outputs": {
            "White Mulberry": REPO_ROOT / "data" / "input" / "vendor_soh_wm.csv",
        },
    },
}

SNAPSHOT_COLS = [
    "SKU", "ASIN", "Brand", "Model",
    "category_l0", "category_l1", "category_l2",
    "NLC", "Qty", "Channel", "Type", "Week",
    # Extras (kept for ops visibility; the service only reads channel=="1p" + Qty)
    "OpenPOUnits", "Aged90PlusUnits", "UnsellableUnits",
    "SellableCost", "SnapshotDate",
]


def get_access_token(acct: str) -> str:
    cid = os.environ.get(f"SP_LWA_CLIENT_ID_{acct}")     or os.environ.get("SP_LWA_CLIENT_ID")
    sec = os.environ.get(f"SP_LWA_CLIENT_SECRET_{acct}") or os.environ.get("SP_LWA_CLIENT_SECRET")
    rt  = os.environ.get(f"SP_API_VENDOR_REFRESH_TOKEN_{acct}")
    if not rt:
        raise SystemExit(f"❌ Missing SP_API_VENDOR_REFRESH_TOKEN_{acct} in .env")
    if not cid or not sec:
        raise SystemExit(f"❌ Missing LWA creds for {acct}")
    r = requests.post(LWA_URL, data={
        "grant_type": "refresh_token", "refresh_token": rt,
        "client_id": cid, "client_secret": sec,
    }, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"❌ LWA failed for {acct}: HTTP {r.status_code} {r.text[:300]}")
    return r.json()["access_token"]


def most_recent_saturday(reference: datetime | None = None) -> str:
    """Return the most recent Saturday on or before (reference - 2d) as 'YYYY-MM-DD'.
    Convention: operator's week ends Saturday; SP-API needs ~48h data lag."""
    ref = (reference or datetime.now(timezone.utc)) - timedelta(days=2)
    # Python weekday(): Mon=0..Sun=6 -> Saturday=5
    offset = (ref.weekday() - 5) % 7
    sat = (ref - timedelta(days=offset)).date()
    return sat.isoformat()


class DataNotAvailable(Exception):
    """Amazon says data for the requested range isn't published yet."""


def pull_vendor_inventory(token: str, snapshot_date: str) -> list[dict]:
    """Request GET_VENDOR_INVENTORY_REPORT, poll till DONE, return inventoryByAsin list.
    Raises DataNotAvailable if Amazon reports the date range isn't published yet."""
    headers = {"x-amz-access-token": token, "Content-Type": "application/json"}
    end_dt = datetime.fromisoformat(snapshot_date).replace(tzinfo=timezone.utc, hour=23, minute=59, second=59)
    start_dt = end_dt - timedelta(days=6)
    end   = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "reportType": "GET_VENDOR_INVENTORY_REPORT",
        "marketplaceIds": [MARKETPLACE_ID],
        "dataStartTime": start, "dataEndTime": end,
        "reportOptions": {
            "reportPeriod": "DAY",
            "distributorView": "MANUFACTURING",
            "sellingProgram": "RETAIL",
        },
    }
    print(f"  create report: {start} -> {end}")
    r = requests.post(f"{SPAPI_HOST}/reports/2021-06-30/reports", json=body, headers=headers, timeout=30)
    if r.status_code != 202:
        raise SystemExit(f"❌ create report failed: HTTP {r.status_code} {r.text[:300]}")
    rep_id = r.json()["reportId"]
    print(f"  reportId: {rep_id}")

    doc_id = None
    for i in range(180):  # 15 min max — Amazon's queue is occasionally slow
        time.sleep(5)
        rr = requests.get(f"{SPAPI_HOST}/reports/2021-06-30/reports/{rep_id}",
                          headers={"x-amz-access-token": token}, timeout=30)
        if rr.status_code != 200:
            continue
        j = rr.json()
        status = j.get("processingStatus")
        print(f"  poll[{i}]: {status}")
        if status == "DONE":
            doc_id = j.get("reportDocumentId")
            break
        if status in ("FATAL", "CANCELLED"):
            doc_id = j.get("reportDocumentId")  # may contain error JSON
            err_text = _read_error_doc(token, doc_id) if doc_id else ""
            if "not yet available" in err_text.lower():
                raise DataNotAvailable(err_text.strip())
            print(f"  FATAL body: {err_text[:600]}")
            raise SystemExit(f"❌ report {status}")
    if not doc_id:
        raise SystemExit("❌ timed out waiting for report")

    rd = requests.get(f"{SPAPI_HOST}/reports/2021-06-30/documents/{doc_id}",
                      headers={"x-amz-access-token": token}, timeout=30)
    rd.raise_for_status()
    doc = rd.json()
    dl = requests.get(doc["url"], timeout=120)
    dl.raise_for_status()
    raw = dl.content
    if doc.get("compressionAlgorithm") == "GZIP":
        import gzip
        raw = gzip.decompress(raw)
    payload = json.loads(raw.decode("utf-8", errors="replace"))
    by_asin = payload.get("inventoryByAsin", []) or []
    return by_asin


def _read_error_doc(token: str, doc_id: str) -> str:
    rd = requests.get(f"{SPAPI_HOST}/reports/2021-06-30/documents/{doc_id}",
                      headers={"x-amz-access-token": token}, timeout=30)
    if rd.status_code != 200:
        return ""
    doc = rd.json()
    dl = requests.get(doc["url"], timeout=60)
    if dl.status_code != 200:
        return ""
    raw = dl.content
    if doc.get("compressionAlgorithm") == "GZIP":
        import gzip
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    return raw.decode("utf-8", errors="replace")


def latest_snapshot(rows: list[dict], target_date: str | None = None) -> pd.DataFrame:
    """Return a DataFrame for the requested date (or most recent if target missing)."""
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["startDate"] = df["startDate"].astype(str)
    if target_date and (df["startDate"] == target_date).any():
        chosen = target_date
    else:
        chosen = df["startDate"].max()
        if target_date:
            print(f"  ⚠ target {target_date} not in response, falling back to latest {chosen}")
    snap = df[df["startDate"] == chosen].copy()

    def _amt(x):
        if isinstance(x, dict):
            return x.get("amount")
        return None

    snap["SellableCost"] = snap.get("sellableOnHandInventoryCost", pd.Series([None]*len(snap))).apply(_amt)
    out = pd.DataFrame({
        "ASIN":            snap["asin"].astype(str).str.strip().str.upper(),
        "Qty":             pd.to_numeric(snap.get("sellableOnHandInventoryUnits"), errors="coerce").fillna(0).astype(int),
        "OpenPOUnits":     pd.to_numeric(snap.get("openPurchaseOrderUnits"),  errors="coerce").fillna(0).astype(int),
        "Aged90PlusUnits": pd.to_numeric(snap.get("aged90PlusDaysSellableInventoryUnits"), errors="coerce").fillna(0).astype(int),
        "UnsellableUnits": pd.to_numeric(snap.get("unsellableOnHandInventoryUnits"), errors="coerce").fillna(0).astype(int),
        "SellableCost":    pd.to_numeric(snap["SellableCost"], errors="coerce"),
        "SnapshotDate":    chosen,
    })
    return out


def annotate_with_master(df: pd.DataFrame) -> pd.DataFrame:
    """Join sku_master to add Brand / Model / category for each ASIN."""
    if df.empty:
        return df
    sm_path = REPO_ROOT / "data" / "input" / "sku_master.xlsx"
    if not sm_path.exists():
        df["Brand"] = ""
        df["Model"] = ""
        return df
    sm = pd.read_excel(sm_path)
    sm.columns = sm.columns.str.strip()
    sm["ASIN"] = sm["ASIN"].astype(str).str.strip().str.upper()
    keep = ["ASIN", "Brand", "Model", "category_l0", "category_l1", "category_l2", "NLC", "FBA SKU"]
    sm = sm[[c for c in keep if c in sm.columns]].drop_duplicates(subset=["ASIN"], keep="first")
    sm = sm.rename(columns={"FBA SKU": "SKU"})
    out = df.merge(sm, on="ASIN", how="left")
    return out


def write_brand_csv(df: pd.DataFrame, brand: str, out_path: Path) -> int:
    sub = df[df["Brand"].astype(str).str.strip().str.lower() == brand.lower()].copy()
    if sub.empty:
        print(f"  ⚠ no ASINs matched brand={brand}")
    sub["Channel"] = "1p"
    sub["Type"] = ""
    sub["Week"] = ""
    # ensure all expected columns exist
    for col in SNAPSHOT_COLS:
        if col not in sub.columns:
            sub[col] = ""
    sub = sub[SNAPSHOT_COLS]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sub.to_csv(out_path, index=False)
    print(f"  -> {out_path.relative_to(REPO_ROOT)}  ({len(sub)} rows, sum Qty={int(sub['Qty'].sum())})")
    return len(sub)


def run_account(acct: str, snapshot_date: str, fallback_days: int = 3) -> None:
    cfg = ACCOUNTS[acct]
    print(f"\n=== {acct} (target {snapshot_date}) ===")
    tok = get_access_token(acct)

    # Walk back up to `fallback_days` if Amazon says data isn't published yet.
    rows = None
    effective_date = snapshot_date
    for attempt in range(fallback_days + 1):
        try_date = (datetime.fromisoformat(snapshot_date).date() - timedelta(days=attempt)).isoformat()
        try:
            rows = pull_vendor_inventory(tok, try_date)
            effective_date = try_date
            if attempt > 0:
                print(f"  ⚠ fell back from {snapshot_date} to {try_date} (Amazon hadn't published target yet)")
            break
        except DataNotAvailable as e:
            print(f"  data not available for {try_date}; trying earlier date")
            continue
    if rows is None:
        print(f"  ❌ gave up after {fallback_days+1} attempts; latest tried = {try_date}")
        return

    print(f"  inventoryByAsin rows pulled: {len(rows)}")
    snap = latest_snapshot(rows, effective_date)
    if snap.empty:
        print(f"  ⚠ no SOH rows for {acct}")
        return
    print(f"  latest date: {snap['SnapshotDate'].iat[0]}, ASINs={len(snap)}, sellable={int(snap['Qty'].sum())}")
    annotated = annotate_with_master(snap)
    # Brands present in the report (after master join):
    present = annotated["Brand"].astype(str).str.strip().value_counts().to_dict()
    print(f"  brand split (per sku_master): {present}")
    for brand, out_path in cfg["outputs"].items():
        write_brand_csv(annotated, brand, out_path)

    # Surface ASINs that aren't in sku_master — operational hygiene signal.
    unm = annotated[annotated["Brand"].isna() | (annotated["Brand"].astype(str).str.lower() == "nan")].copy()
    if not unm.empty:
        unm_path = REPO_ROOT / "data" / "input" / f"vendor_soh_unmatched_{acct.lower()}.csv"
        unm_cols = ["ASIN", "Qty", "OpenPOUnits", "Aged90PlusUnits", "UnsellableUnits", "SellableCost", "SnapshotDate"]
        unm = unm.sort_values("Qty", ascending=False)
        unm[unm_cols].to_csv(unm_path, index=False)
        print(f"  ⚠ {len(unm)} ASINs missing from sku_master  (SOH={int(unm['Qty'].sum())})  -> {unm_path.relative_to(REPO_ROOT)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", choices=list(ACCOUNTS.keys()) + ["ALL"], default="ALL")
    ap.add_argument("--date", default=None,
                    help="Snapshot date YYYY-MM-DD (default: most recent Saturday with 48h data lag)")
    args = ap.parse_args()
    load_dotenv(REPO_ROOT / ".env")
    snap_date = args.date or most_recent_saturday()
    print(f"Snapshot date: {snap_date}")
    targets = list(ACCOUNTS.keys()) if args.account == "ALL" else [args.account]
    for acct in targets:
        run_account(acct, snap_date)


if __name__ == "__main__":
    main()
