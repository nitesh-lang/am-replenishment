"""
SP-API FBA Storage & Capacity Pull
===================================

Pulls two Amazon reports and writes them to data/input/ per account:

1. GET_FBA_STORAGE_FEE_CHARGES_DATA -> storage_by_fc_<account>.csv
   PER-FC schema: asin, fnsku, fulfillment-center, item-volume (cbm),
   average-quantity-on-hand, estimated-total-item-volume,
   storage-rate, estimated-monthly-storage-fee.
   This is the closest thing SP-API exposes to "how much space am I
   using at each FC" — Amazon doesn't publish per-FC capacity limits
   per seller, but this report shows actual per-FC footprint.

2. GET_FBA_INVENTORY_PLANNING_DATA -> storage_planning_<account>.csv
   SKU × marketplace schema: available, inv-age buckets (0-90/91-180
   /181-270/271-365/365+), long-term-storage-fee quantities, cbm per
   unit. Useful for aged / stranded inventory tracking.

Accounts (extends CAMBIUMRETAIL via the same LWA-override pattern
in .env; see reference_sp_api_lwa_token_binding memory):
    NEXLEV / VIOMI / AUDIOARRAY / WHITEMULBERRY / CAMBIUMRETAIL

Usage:
    python scripts/sp_storage_capacity_pull.py                 # all accounts
    python scripts/sp_storage_capacity_pull.py --account NEXLEV
    python scripts/sp_storage_capacity_pull.py --report fee    # only per-FC storage
    python scripts/sp_storage_capacity_pull.py --report plan   # only planning
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

LWA_URL        = "https://api.amazon.com/auth/o2/token"
SPAPI_HOST     = "https://sellingpartnerapi-eu.amazon.com"
MARKETPLACE_ID = "A21TJRUUN4KGV"  # amazon.in

REPO    = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "data" / "input"

# account key -> (fee-report-file, planning-report-file)
# CAMBIUMRETAIL uses per-account LWA overrides (see .env)
ACCOUNTS = {
    "NEXLEV":        ("storage_by_fc_nexlev.csv",        "storage_planning_nexlev.csv"),
    "VIOMI":         ("storage_by_fc_viomi.csv",         "storage_planning_viomi.csv"),
    "AUDIOARRAY":    ("storage_by_fc_audio_array.csv",   "storage_planning_audio_array.csv"),
    "WHITEMULBERRY": ("storage_by_fc_WM.csv",            "storage_planning_WM.csv"),
    "CAMBIUMRETAIL": ("Fossil Replenishment/storage_by_fc_fossil.csv",
                      "Fossil Replenishment/storage_planning_fossil.csv"),
}

REPORT_FEE  = "GET_FBA_STORAGE_FEE_CHARGES_DATA"
REPORT_PLAN = "GET_FBA_INVENTORY_PLANNING_DATA"


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


def pull_report(token: str, report_type: str, start_iso: str, end_iso: str) -> bytes:
    body = {
        "reportType": report_type,
        "marketplaceIds": [MARKETPLACE_ID],
        "dataStartTime": start_iso,
        "dataEndTime":   end_iso,
    }
    r = requests.post(f"{SPAPI_HOST}/reports/2021-06-30/reports",
                      json=body,
                      headers={"x-amz-access-token": token,
                               "Content-Type": "application/json"},
                      timeout=30)
    if r.status_code != 202:
        raise SystemExit(f"❌ create {report_type} failed: HTTP {r.status_code} {r.text[:300]}")
    rid = r.json()["reportId"]
    print(f"  reportId: {rid}")

    doc_id = None
    for i in range(180):  # 15 min max
        time.sleep(5)
        rr = requests.get(f"{SPAPI_HOST}/reports/2021-06-30/reports/{rid}",
                          headers={"x-amz-access-token": token}, timeout=30)
        if rr.status_code != 200:
            continue
        j = rr.json()
        status = j.get("processingStatus")
        if i % 3 == 0:
            print(f"  poll[{i}]: {status}")
        if status == "DONE":
            doc_id = j.get("reportDocumentId")
            break
        if status in ("FATAL", "CANCELLED"):
            print(f"  {status} — {report_type} not available for this window")
            return b""
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
    return raw


def tsv_to_csv(raw: bytes, out_path: Path) -> tuple[int, list[str]]:
    if not raw:
        return 0, []
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    rows = list(reader)
    if not rows:
        return 0, []
    header = rows[0]
    body   = rows[1:]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    return len(body), header


def run_account(acct: str, do_fee: bool, do_plan: bool) -> None:
    print(f"\n=== {acct} ===")
    tok = get_access_token(acct)
    now = datetime.now(timezone.utc)
    # Storage fee report is monthly; give a 60-day window so any recent
    # month's report is picked up. Planning report is a live snapshot.
    end_iso   = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_iso = (now - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")

    fee_file, plan_file = ACCOUNTS[acct]

    if do_fee:
        print(f"  → {REPORT_FEE}")
        raw = pull_report(tok, REPORT_FEE, start_iso, end_iso)
        rows, header = tsv_to_csv(raw, OUT_DIR / fee_file)
        print(f"  wrote {rows} rows -> {fee_file} ({len(header)} columns)")

    if do_plan:
        print(f"  → {REPORT_PLAN}")
        raw = pull_report(tok, REPORT_PLAN, start_iso, end_iso)
        rows, header = tsv_to_csv(raw, OUT_DIR / plan_file)
        print(f"  wrote {rows} rows -> {plan_file} ({len(header)} columns)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", choices=list(ACCOUNTS.keys()) + ["ALL"], default="ALL")
    ap.add_argument("--report",  choices=["fee", "plan", "both"], default="both")
    args = ap.parse_args()

    load_dotenv(REPO / ".env")
    do_fee  = args.report in ("fee", "both")
    do_plan = args.report in ("plan", "both")
    targets = list(ACCOUNTS.keys()) if args.account == "ALL" else [args.account]
    for a in targets:
        run_account(a, do_fee, do_plan)


if __name__ == "__main__":
    main()
