"""
SP-API FBA Sales Pull (3P seller accounts)
==========================================

Pulls GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL — one row per
shipped item with all order/shipment/buyer/FC/pricing fields. Same
schema as the manual All Orders downloads currently landing in
data/input/FBA Sales/Week NN/<Account>.csv.

Accounts (3P seller): NEXLEV / VIOMI / AUDIOARRAY / WHITEMULBERRY
Report contains only orders in the requested date range (order-date basis).
Marketplace: amazon.in (A21TJRUUN4KGV)

Required env vars (.env):
    SP_LWA_CLIENT_ID + SP_LWA_CLIENT_SECRET (or per-account overrides)
    SP_REFRESH_TOKEN_<ACCOUNT>

Usage:
    python scripts/sp_sales_pull.py --start 2026-06-28 --end 2026-07-04 --week 27
    python scripts/sp_sales_pull.py --start 2026-06-28 --end 2026-07-04 --week 27 --account NEXLEV
"""
from __future__ import annotations

import argparse
import functools
import io
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except Exception:
    pass
print = functools.partial(print, flush=True)

LWA_URL        = "https://api.amazon.com/auth/o2/token"
SPAPI_HOST     = "https://sellingpartnerapi-eu.amazon.com"
MARKETPLACE_ID = "A21TJRUUN4KGV"

REPO = Path(__file__).resolve().parent.parent

# env-suffix -> per-account CSV filename (matches manual download naming)
ACCOUNTS = {
    "NEXLEV":         "Nexlev.csv",
    "VIOMI":          "Viomi.csv",
    "AUDIOARRAY":     "Audio Array.csv",
    "WHITEMULBERRY":  "White Mulberry.csv",
    "CAMBIUMRETAIL":  "Cambium Retail.csv",
    # CRPL not included — no seller token available yet.
}

# Amazon-fulfilled shipments (FBA-only) — matches the schema of the
# manual Seller Central "Fulfillment / All Orders" download: includes
# Shipment ID, Shipment Date, FC, Tracking Number, etc. Naturally filters
# out MFN (merchant-fulfilled) orders since it's Amazon-fulfilled only.
REPORT_TYPE = "GET_AMAZON_FULFILLED_SHIPMENTS_DATA_GENERAL"


def get_access_token(acct: str) -> str:
    cid = os.environ.get(f"SP_LWA_CLIENT_ID_{acct}")     or os.environ.get("SP_LWA_CLIENT_ID")
    sec = os.environ.get(f"SP_LWA_CLIENT_SECRET_{acct}") or os.environ.get("SP_LWA_CLIENT_SECRET")
    rt  = os.environ.get(f"SP_REFRESH_TOKEN_{acct}")
    if not rt:
        raise SystemExit(f"❌ Missing SP_REFRESH_TOKEN_{acct} in .env")
    if not cid or not sec:
        raise SystemExit(f"❌ Missing LWA creds for {acct}")
    r = requests.post(LWA_URL, data={
        "grant_type": "refresh_token", "refresh_token": rt,
        "client_id": cid, "client_secret": sec,
    }, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"❌ LWA failed for {acct}: HTTP {r.status_code} {r.text[:300]}")
    return r.json()["access_token"]


def pull_all_orders(token: str, start: date, end: date) -> bytes:
    """Request the All-Orders report for the window, poll to DONE, return raw TSV bytes."""
    headers = {"x-amz-access-token": token, "Content-Type": "application/json"}
    # Include the full end-day: 00:00:00Z start, 23:59:59Z end
    start_ts = datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_ts   = datetime.combine(end,   datetime.max.time()).replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "reportType": REPORT_TYPE,
        "marketplaceIds": [MARKETPLACE_ID],
        "dataStartTime": start_ts,
        "dataEndTime":   end_ts,
    }
    print(f"  create report: {start} -> {end}")
    r = requests.post(f"{SPAPI_HOST}/reports/2021-06-30/reports",
                      json=body, headers=headers, timeout=30)
    if r.status_code != 202:
        raise SystemExit(f"❌ create report failed: HTTP {r.status_code} {r.text[:300]}")
    rep_id = r.json()["reportId"]
    print(f"  reportId: {rep_id}")

    doc_id = None
    for i in range(180):
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
            doc_id = j.get("reportDocumentId")
            err_text = _read_error_doc(token, doc_id) if doc_id else ""
            print(f"  FATAL body: {err_text[:600]}")
            raise SystemExit(f"❌ report {status}")
    if not doc_id:
        raise SystemExit("❌ timed out waiting for report")

    rd = requests.get(f"{SPAPI_HOST}/reports/2021-06-30/documents/{doc_id}",
                      headers={"x-amz-access-token": token}, timeout=30)
    rd.raise_for_status()
    doc = rd.json()
    dl = requests.get(doc["url"], timeout=180)
    dl.raise_for_status()
    raw = dl.content
    if doc.get("compressionAlgorithm") == "GZIP":
        import gzip
        raw = gzip.decompress(raw)
    return raw


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


def _load_master_skus() -> set[str] | None:
    """sku_master's FBA SKU column, uppercased. Returns None if not readable."""
    try:
        import pandas as pd
        sm = pd.read_excel(REPO / "data" / "input" / "sku_master.xlsx")
        sm.columns = sm.columns.str.strip()
        return set(sm["FBA SKU"].astype(str).str.strip().str.upper())
    except Exception as e:
        print(f"  ! sku_master load failed ({e}); skipping master-SKU filter")
        return None


def tsv_to_csv(raw: bytes, out_path: Path, filter_master_skus: bool = True) -> tuple[int, int]:
    """Report is TSV; write to CSV.
    When filter_master_skus=True, keep only rows whose Merchant SKU is in
    sku_master.xlsx — matches the "master SKUs only" convention.
    Returns (kept_rows, dropped_rows)."""
    import csv
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    rows = list(reader)
    if not rows:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        return 0, 0

    header = rows[0]
    body   = rows[1:]

    kept, dropped = body, []
    if filter_master_skus:
        master_skus = _load_master_skus()
        if master_skus is not None:
            # Merchant SKU column position — case-insensitive header match
            sku_idx = next(
                (i for i, h in enumerate(header)
                 if h.strip().lower() in ("merchant sku", "sku", "seller sku")),
                None,
            )
            if sku_idx is not None:
                kept, dropped = [], []
                for r in body:
                    if len(r) > sku_idx and r[sku_idx].strip().upper() in master_skus:
                        kept.append(r)
                    else:
                        dropped.append(r)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(kept)
    return len(kept), len(dropped)


def run_account(acct: str, start: date, end: date, week: int,
                filter_master: bool = True) -> None:
    fname = ACCOUNTS[acct]
    out_path = REPO / "data" / "input" / "FBA Sales" / f"Week {week}" / fname
    print(f"\n=== {acct}  {start} -> {end}  → Week {week}/{fname} ===")
    tok = get_access_token(acct)
    raw = pull_all_orders(tok, start, end)
    kept, dropped = tsv_to_csv(raw, out_path, filter_master_skus=filter_master)
    tag = f" (dropped {dropped} non-master SKU rows)" if dropped else ""
    print(f"  wrote {kept} rows{tag} -> {out_path.relative_to(REPO)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", choices=list(ACCOUNTS.keys()) + ["ALL"], default="ALL")
    ap.add_argument("--start", required=True, help="Start date YYYY-MM-DD (inclusive)")
    ap.add_argument("--end",   required=True, help="End date YYYY-MM-DD (inclusive)")
    ap.add_argument("--week",  required=True, type=int,
                    help="Sun-Sat week number for output subfolder (e.g., 27)")
    ap.add_argument("--no-filter-master", action="store_true",
                    help="Skip the sku_master filter and keep every row")
    args = ap.parse_args()

    load_dotenv(REPO / ".env")

    start = datetime.fromisoformat(args.start).date()
    end   = datetime.fromisoformat(args.end).date()
    if end < start:
        raise SystemExit("❌ --end must be >= --start")

    targets = list(ACCOUNTS.keys()) if args.account == "ALL" else [args.account]
    for acct in targets:
        run_account(acct, start, end, args.week,
                    filter_master=not args.no_filter_master)


if __name__ == "__main__":
    main()
