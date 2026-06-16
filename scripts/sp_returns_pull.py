"""
SP-API FBA Customer Returns Pull (3P / Seller)
==============================================

Pulls FBA customer returns via the Reports API for the last N days (default 90).

Report: GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA
Output: data/input/fba_returns_<account>.csv

Columns from Amazon (TSV converted to CSV):
    return-date, order-id, sku, asin, fnsku, product-name, quantity,
    fulfillment-center-id, detailed-disposition, reason,
    license-plate-number, customer-comments

Required env vars in .env:
    SP_REFRESH_TOKEN_<ACCOUNT>
    SP_LWA_CLIENT_ID         (or SP_LWA_CLIENT_ID_<ACCOUNT>)
    SP_LWA_CLIENT_SECRET     (or SP_LWA_CLIENT_SECRET_<ACCOUNT>)

Usage:
    python scripts/sp_returns_pull.py                          # nexlev, 90d
    python scripts/sp_returns_pull.py --account nexlev --days 30
    python scripts/sp_returns_pull.py --account nexlev --days 90
"""
from __future__ import annotations

import argparse
import csv
import functools
import gzip
import io
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
REPORT_TYPE    = "GET_FBA_FULFILLMENT_CUSTOMER_RETURNS_DATA"
REPO_ROOT      = Path(__file__).resolve().parent.parent

ACCOUNT_SLUGS = {
    "nexlev":      "nexlev",
    "viomi":       "viomi",
    "audio_array": "audio_array",
    "wm":          "wm",
    "fossil":      "fossil",
}


def output_path(account: str) -> Path:
    slug = ACCOUNT_SLUGS.get(account, account.lower().replace(" ", "_"))
    return REPO_ROOT / "data" / "input" / f"fba_returns_{slug}.csv"


def get_access_token(account: str) -> str:
    acct = account.upper()
    cid = os.environ.get(f"SP_LWA_CLIENT_ID_{acct}")     or os.environ.get("SP_LWA_CLIENT_ID")
    sec = os.environ.get(f"SP_LWA_CLIENT_SECRET_{acct}") or os.environ.get("SP_LWA_CLIENT_SECRET")
    rt  = os.environ.get(f"SP_REFRESH_TOKEN_{acct}")
    if not rt:
        raise SystemExit(f"❌ Missing SP_REFRESH_TOKEN_{acct} in .env")
    if not cid or not sec:
        raise SystemExit(f"❌ Missing LWA creds for {acct}. Provide either "
                         f"SP_LWA_CLIENT_ID_{acct} + SP_LWA_CLIENT_SECRET_{acct}, "
                         f"or the shared SP_LWA_CLIENT_ID + SP_LWA_CLIENT_SECRET.")
    r = requests.post(LWA_URL, data={
        "grant_type": "refresh_token", "refresh_token": rt,
        "client_id": cid, "client_secret": sec,
    }, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"❌ LWA failed for {acct}: HTTP {r.status_code} {r.text[:300]}")
    return r.json()["access_token"]


def pull_returns(token: str, days: int) -> str:
    """Create report, poll till DONE, return decoded TSV body."""
    headers = {"x-amz-access-token": token, "Content-Type": "application/json"}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    end   = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "reportType":     REPORT_TYPE,
        "marketplaceIds": [MARKETPLACE_ID],
        "dataStartTime":  start,
        "dataEndTime":    end,
    }
    print(f"  create report: {start} -> {end}")
    r = requests.post(f"{SPAPI_HOST}/reports/2021-06-30/reports",
                      json=body, headers=headers, timeout=30)
    if r.status_code != 202:
        raise SystemExit(f"❌ create failed: HTTP {r.status_code} {r.text[:400]}")
    rep_id = r.json()["reportId"]
    print(f"  reportId: {rep_id}")

    doc_id = None
    for i in range(60):
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
            if doc_id:
                err = _read_error_doc(token, doc_id)
                print(f"  FATAL body: {err[:600]}")
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
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", errors="replace")


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
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    return raw.decode("utf-8", errors="replace")


def tsv_to_csv(tsv_text: str, out_path: Path) -> tuple[int, list[str]]:
    """Write the TSV body to CSV. Returns (row_count, header_columns)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    reader = csv.reader(io.StringIO(tsv_text), delimiter="\t")
    rows = list(reader)
    if not rows:
        return 0, []
    header = rows[0]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerows(rows)
    return len(rows) - 1, header


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default="nexlev", choices=sorted(ACCOUNT_SLUGS.keys()))
    ap.add_argument("--days", type=int, default=90)
    args = ap.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    print(f"→ Account: {args.account}  | Window: {args.days} days")
    print("→ Getting LWA access token…")
    tok = get_access_token(args.account)
    print("  OK")

    print(f"→ Requesting {REPORT_TYPE}")
    body = pull_returns(tok, args.days)

    out_csv = output_path(args.account)
    n, header = tsv_to_csv(body, out_csv)
    print(f"\n✓ Wrote {n} return rows")
    print(f"  columns: {header}")
    print(f"  → {out_csv.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
