"""
SP-API FBA Inventory Ledger Pull
================================

Pulls GET_LEDGER_SUMMARY_VIEW_DATA (per FC, per SKU, per day) — exact same
schema as the CSVs the operator has been downloading manually from Seller
Central. Replaces the manual drop step for Nexlev/Viomi/AA/WM.

Accounts:
    NEXLEV / VIOMI / AUDIO_ARRAY / WM

Output:
    data/input/inventory_ledger_nexlev.csv
    data/input/inventory_ledger_viomi.csv
    data/input/inventory_ledger_Audio Array.csv
    data/input/inventory_ledger_WM.csv

Required env vars (.env):
    SP_LWA_CLIENT_ID / SP_LWA_CLIENT_SECRET  (or per-account overrides)
    SP_REFRESH_TOKEN_NEXLEV
    SP_REFRESH_TOKEN_VIOMI
    SP_REFRESH_TOKEN_AUDIO_ARRAY
    SP_REFRESH_TOKEN_WM

Usage:
    python scripts/sp_ledger_pull.py                       # all accounts, last 7 days
    python scripts/sp_ledger_pull.py --account nexlev      # single account
    python scripts/sp_ledger_pull.py --days 14             # broader window
    python scripts/sp_ledger_pull.py --end-date 2026-07-05 # backdated pull
"""
from __future__ import annotations

import argparse
import csv
import functools
import io
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
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
MARKETPLACE_ID = "A21TJRUUN4KGV"                             # amazon.in

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "data" / "input"

# account key = env var suffix (matches SP_REFRESH_TOKEN_<key> naming)
# → output filename (matches existing inventory_ledger_* convention)
ACCOUNTS = {
    "NEXLEV":        "inventory_ledger_nexlev.csv",
    "VIOMI":         "inventory_ledger_viomi.csv",
    "AUDIOARRAY":    "inventory_ledger_Audio Array.csv",
    "WHITEMULBERRY": "inventory_ledger_WM.csv",
}


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


class DataNotAvailable(Exception):
    pass


def pull_ledger(token: str, start_date: date, end_date: date) -> bytes:
    """Request GET_LEDGER_SUMMARY_VIEW_DATA, poll till DONE, return raw TSV bytes.

    - aggregateByLocation = FC   → one row per (FC, SKU, disposition, date)
    - aggregatedByTimePeriod = DAILY → one row per day within the window
    """
    headers = {"x-amz-access-token": token, "Content-Type": "application/json"}
    start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end   = datetime.combine(end_date,   datetime.max.time()).replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "reportType": "GET_LEDGER_SUMMARY_VIEW_DATA",
        "marketplaceIds": [MARKETPLACE_ID],
        "dataStartTime": start,
        "dataEndTime":   end,
        "reportOptions": {
            "aggregateByLocation":    "FC",
            "aggregatedByTimePeriod": "DAILY",
        },
    }
    print(f"  create report: {start_date} -> {end_date}")
    r = requests.post(f"{SPAPI_HOST}/reports/2021-06-30/reports",
                      json=body, headers=headers, timeout=30)
    if r.status_code != 202:
        raise SystemExit(f"❌ create report failed: HTTP {r.status_code} {r.text[:300]}")
    rep_id = r.json()["reportId"]
    print(f"  reportId: {rep_id}")

    doc_id = None
    for i in range(180):  # 15 min max
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


def tsv_to_csv(raw: bytes, out_path: Path) -> tuple[int, str]:
    """Convert the TSV report to CSV, matching the manual download format.
    Returns (rows_written, latest_date_string).
    Amazon delivers ledger reports as TSV with date format MM-DD-YYYY.
    """
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    rows = list(reader)
    if not rows:
        return 0, ""
    header = rows[0]
    body   = rows[1:]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)

    # Peek latest date for logging (column may be "Date")
    date_idx = next((i for i, h in enumerate(header) if h.strip().lower() == "date"), None)
    latest = ""
    if date_idx is not None and body:
        latest = max((r[date_idx] for r in body if len(r) > date_idx), default="")
    return len(body), latest


def run_account(acct: str, start_date: date, end_date: date, fallback_days: int = 3) -> None:
    print(f"\n=== {acct}  ({start_date} -> {end_date}) ===")
    tok = get_access_token(acct)

    raw = None
    effective_end = end_date
    for attempt in range(fallback_days + 1):
        try_end = end_date - timedelta(days=attempt)
        try_start = start_date - timedelta(days=attempt)
        try:
            raw = pull_ledger(tok, try_start, try_end)
            effective_end = try_end
            if attempt > 0:
                print(f"  ⚠ fell back to {try_start}..{try_end} (Amazon hadn't published target yet)")
            break
        except DataNotAvailable:
            print(f"  data not available for {try_end}; trying earlier")
            continue
    if raw is None:
        print(f"  ❌ gave up after {fallback_days + 1} attempts")
        return

    out_path = OUT_DIR / ACCOUNTS[acct]
    rows_written, latest = tsv_to_csv(raw, out_path)
    print(f"  wrote {rows_written} rows, latest date {latest or 'n/a'} -> {out_path.relative_to(REPO)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", choices=list(ACCOUNTS.keys()) + ["ALL"], default="ALL")
    ap.add_argument("--days", type=int, default=7,
                    help="Days of history to include (default: 7)")
    ap.add_argument("--end-date", default=None,
                    help="End date YYYY-MM-DD (default: today minus ~2d data lag)")
    args = ap.parse_args()

    load_dotenv(REPO / ".env")

    if args.end_date:
        end = datetime.fromisoformat(args.end_date).date()
    else:
        end = date.today() - timedelta(days=2)  # Amazon ledger has ~2-day lag
    start = end - timedelta(days=args.days - 1)

    print(f"Requested window: {start} -> {end}")
    targets = list(ACCOUNTS.keys()) if args.account == "ALL" else [args.account]
    for acct in targets:
        run_account(acct, start, end)


if __name__ == "__main__":
    main()
