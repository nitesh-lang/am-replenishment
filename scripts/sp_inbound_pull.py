"""
SP-API Inbound Shipment Pull — Nexlev (India / amazon.in)
=========================================================

Pulls the two FBA inbound-shipment reports from Selling Partner API and
joins them into a single per-SKU per-FC CSV.

    GET_FBA_FULFILLMENT_INBOUND_SHIPMENT_DATA       (one row per shipment)
    GET_FBA_FULFILLMENT_INBOUND_SHIPMENT_ITEM_DATA  (one row per shipment × SKU)

Output: data/input/inbound_shipments_nexlev.csv

Required env vars (in .env at repo root):
    SP_LWA_CLIENT_ID
    SP_LWA_CLIENT_SECRET
    SP_REFRESH_TOKEN_NEXLEV
    SP_MERCHANT_ID_NEXLEV         (informational — not used in the API call)

Usage:
    python scripts/sp_inbound_pull.py
    python scripts/sp_inbound_pull.py --days 90      (default 60)

No third-party SP-API library — just `requests` + `pandas` + `python-dotenv`.
"""

from __future__ import annotations

import argparse
import gzip
import io
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────────────
# Constants — India / amazon.in
# ──────────────────────────────────────────────────────────────────────
LWA_URL          = "https://api.amazon.com/auth/o2/token"
SPAPI_HOST       = "https://sellingpartnerapi-eu.amazon.com"  # EU region (amazon.in lives here per Amazon)
MARKETPLACE_ID   = "A21TJRUUN4KGV"                            # amazon.in
HEADER_REPORT    = "GET_FBA_FULFILLMENT_INBOUND_SHIPMENT_DATA"
ITEM_REPORT      = "GET_FBA_FULFILLMENT_INBOUND_SHIPMENT_ITEM_DATA"

REPO_ROOT  = Path(__file__).resolve().parent.parent
OUTPUT_CSV = REPO_ROOT / "data" / "input" / "inbound_shipments_nexlev.csv"


# ──────────────────────────────────────────────────────────────────────
# Auth — refresh-token → access-token (~1 hour)
# ──────────────────────────────────────────────────────────────────────
def get_access_token() -> str:
    payload = {
        "grant_type":    "refresh_token",
        "refresh_token": os.environ["SP_REFRESH_TOKEN_NEXLEV"],
        "client_id":     os.environ["SP_LWA_CLIENT_ID"],
        "client_secret": os.environ["SP_LWA_CLIENT_SECRET"],
    }
    r = requests.post(LWA_URL, data=payload, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def _h(token: str) -> dict:
    return {"x-amz-access-token": token, "Content-Type": "application/json"}


# ──────────────────────────────────────────────────────────────────────
# Reports API — request → poll → download → parse
# ──────────────────────────────────────────────────────────────────────
def request_report(token: str, report_type: str, since: datetime) -> str:
    """Submit a report request and return the reportId."""
    body = {
        "reportType":       report_type,
        "marketplaceIds":   [MARKETPLACE_ID],
        "dataStartTime":    since.isoformat(),
    }
    r = requests.post(
        f"{SPAPI_HOST}/reports/2021-06-30/reports",
        headers=_h(token),
        json=body,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["reportId"]


def wait_for_report(token: str, report_id: str, max_wait_sec: int = 600) -> str:
    """Poll until DONE, return reportDocumentId. Raises if FATAL/CANCELLED."""
    start = time.time()
    delay = 10
    while True:
        r = requests.get(
            f"{SPAPI_HOST}/reports/2021-06-30/reports/{report_id}",
            headers=_h(token),
            timeout=30,
        )
        r.raise_for_status()
        info   = r.json()
        status = info["processingStatus"]
        print(f"  report {report_id[:14]}… status={status}")
        if status == "DONE":
            return info["reportDocumentId"]
        if status in ("FATAL", "CANCELLED"):
            raise RuntimeError(f"Report {report_id} ended in {status}: {info}")
        if time.time() - start > max_wait_sec:
            raise TimeoutError(f"Report {report_id} did not finish in {max_wait_sec}s")
        time.sleep(delay)
        delay = min(delay + 5, 30)


def download_report(token: str, doc_id: str) -> pd.DataFrame:
    """Get document URL, download, decompress if gzip, parse TSV → DataFrame."""
    r = requests.get(
        f"{SPAPI_HOST}/reports/2021-06-30/documents/{doc_id}",
        headers=_h(token),
        timeout=30,
    )
    r.raise_for_status()
    doc = r.json()
    url = doc["url"]
    raw = requests.get(url, timeout=60).content
    if doc.get("compressionAlgorithm") == "GZIP":
        raw = gzip.decompress(raw)
    # SP-API reports are tab-delimited with UTF-8 BOM
    return pd.read_csv(io.BytesIO(raw), sep="\t", encoding="utf-8-sig", dtype=str)


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=60,
                        help="Pull shipments updated within the last N days (default 60)")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")

    required = ["SP_LWA_CLIENT_ID", "SP_LWA_CLIENT_SECRET", "SP_REFRESH_TOKEN_NEXLEV"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"❌ Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    print(f"→ Pulling SP-API inbound shipments for Nexlev since {since.date()}")

    token = get_access_token()
    print("✓ Got LWA access token")

    # 1. Shipment headers
    print(f"\n→ Requesting {HEADER_REPORT}…")
    hdr_id  = request_report(token, HEADER_REPORT, since)
    hdr_doc = wait_for_report(token, hdr_id)
    df_hdr  = download_report(token, hdr_doc)
    print(f"  headers: {len(df_hdr)} shipments, cols={list(df_hdr.columns)[:6]}…")

    # 2. Shipment items
    print(f"\n→ Requesting {ITEM_REPORT}…")
    itm_id  = request_report(token, ITEM_REPORT, since)
    itm_doc = wait_for_report(token, itm_id)
    df_itm  = download_report(token, itm_doc)
    print(f"  items: {len(df_itm)} rows, cols={list(df_itm.columns)[:6]}…")

    # 3. Join on ShipmentId. Both reports use ShipmentId; fall back if Amazon
    #    has changed the column casing.
    def pick_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    hdr_key = pick_col(df_hdr, ["ShipmentId", "shipment-id", "shipmentId"])
    itm_key = pick_col(df_itm, ["ShipmentId", "shipment-id", "shipmentId"])
    if not hdr_key or not itm_key:
        raise RuntimeError("Could not find ShipmentId column in either report")

    merged = df_itm.merge(df_hdr, left_on=itm_key, right_on=hdr_key, how="left",
                          suffixes=("_item", "_hdr"))

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(OUTPUT_CSV, index=False)
    print(f"\n✓ Wrote {len(merged)} rows → {OUTPUT_CSV.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
