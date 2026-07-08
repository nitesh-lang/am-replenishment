"""
SP-API FBA Inventory Pull
=========================

Pulls the FBA inventory summary via the direct FBA Inventory API v1
(getInventorySummaries — no report queue, immediate response).

Produces `data/input/inventory_amazon_<slug>.csv` with the same schema
as the manual "All Inventory Report" download from Seller Central.

Accounts: NEXLEV / VIOMI / AUDIOARRAY / WHITEMULBERRY
Endpoint: /fba/inventory/v1/summaries
Marketplace: amazon.in (A21TJRUUN4KGV)

Required env vars (.env):
    SP_LWA_CLIENT_ID + SP_LWA_CLIENT_SECRET (shared) OR per-account override
    SP_REFRESH_TOKEN_<ACCOUNT>

Usage:
    python scripts/sp_fba_inventory_pull.py                 # all 4 accounts
    python scripts/sp_fba_inventory_pull.py --account NEXLEV
"""
from __future__ import annotations

import argparse
import csv
import functools
import os
import sys
import time
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
OUT_DIR = REPO / "data" / "input"

# env key -> output filename (matches existing inventory_amazon_* naming)
ACCOUNTS = {
    "NEXLEV":        "inventory_amazon_nexlev.csv",
    "VIOMI":         "inventory_amazon_viomi.csv",
    "AUDIOARRAY":    "inventory_amazon_audio_array.csv",
    "WHITEMULBERRY": "inventory_amazon_WM.csv",
}

# Output CSV columns (match manual All Inventory Report format)
COLS = [
    "sku", "fnsku", "asin", "product-name", "condition", "your-price",
    "mfn-listing-exists", "mfn-fulfillable-quantity",
    "afn-listing-exists",
    "afn-warehouse-quantity", "afn-fulfillable-quantity",
    "afn-unsellable-quantity", "afn-reserved-quantity",
    "afn-total-quantity", "per-unit-volume",
    "afn-inbound-working-quantity", "afn-inbound-shipped-quantity",
    "afn-inbound-receiving-quantity", "afn-researching-quantity",
    "afn-reserved-future-supply", "afn-future-supply-buyable", "store",
]


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


def fetch_all_summaries(token: str) -> list[dict]:
    """Page through /fba/inventory/v1/summaries until nextToken is empty."""
    headers = {"x-amz-access-token": token}
    out: list[dict] = []
    next_token: str | None = None
    page = 0
    while True:
        page += 1
        params: dict = {
            "details": "true",
            "granularityType": "Marketplace",
            "granularityId":   MARKETPLACE_ID,
            "marketplaceIds":  MARKETPLACE_ID,
        }
        if next_token:
            params["nextToken"] = next_token

        r = requests.get(f"{SPAPI_HOST}/fba/inventory/v1/summaries",
                         params=params, headers=headers, timeout=45)
        if r.status_code == 429:
            print(f"  ! page {page} 429 throttled — sleep 5s")
            time.sleep(5); continue
        if r.status_code != 200:
            print(f"  ! HTTP {r.status_code}: {r.text[:400]}")
        r.raise_for_status()
        body = r.json()
        payload = body.get("payload") or {}
        items = payload.get("inventorySummaries") or []
        out.extend(items)
        next_token = (body.get("pagination") or {}).get("nextToken")
        print(f"  page {page}: {len(items)} items (total {len(out)})")
        if not next_token:
            break
        time.sleep(0.3)  # polite pacing between paged requests
    return out


def _bool_yesno(v) -> str:
    return "Yes" if v else "No"


def _int(v) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def summaries_to_rows(items: list[dict]) -> list[dict]:
    """Map API JSON → CSV row schema."""
    rows: list[dict] = []
    for it in items:
        det = it.get("inventoryDetails") or {}
        inb = det.get("inboundShipmentQuantity") or {}
        research = det.get("researchingQuantity") or {}
        unfill  = det.get("unfulfillableQuantity") or {}
        reserved = det.get("reservedQuantity") or {}
        future = det.get("futureSupplyQuantity") or {}

        working   = _int(inb.get("inboundWorkingQuantity"))
        shipped   = _int(inb.get("inboundShippedQuantity"))
        receiving = _int(inb.get("inboundReceivingQuantity"))
        fulfillable = _int(det.get("fulfillableQuantity"))
        researching = _int(research.get("totalResearchingQuantity"))
        unfulfillable = _int(unfill.get("totalUnfulfillableQuantity"))
        # afn-reserved-quantity in the manual All Inventory Report = only
        # pendingCustomerOrderQuantity (units pre-sold to customer orders,
        # about to ship). SP-API's totalReservedQuantity is a broader
        # bucket that ALSO includes pendingTransshipmentQuantity (units
        # already accounted for in the ledger as In-Transit Between
        # Warehouses) plus fcProcessingQuantity. Using totalReserved would
        # double-deduct transshipment from Real AM Inv.
        reserved_customer_orders = _int(reserved.get("pendingCustomerOrderQuantity"))
        reserved_transship       = _int(reserved.get("pendingTransshipmentQuantity"))
        reserved_fc_processing   = _int(reserved.get("fcProcessingQuantity"))
        reserved_total_broad     = _int(reserved.get("totalReservedQuantity"))
        # Match manual report semantics: afn-reserved = customer orders only.
        reserved_qty = reserved_customer_orders
        reserved_future = _int(future.get("reservedFutureSupply"))
        future_buyable  = _int(future.get("futureSupplyBuyable"))
        # Warehouse quantity mirrors the manual report:
        #   fulfillable + reserved (customer orders) + unfulfillable
        warehouse = fulfillable + reserved_qty + unfulfillable
        total = warehouse + working + shipped + receiving

        rows.append({
            "sku":                  it.get("sellerSku") or "",
            "fnsku":                it.get("fnSku") or "",
            "asin":                 it.get("asin") or "",
            "product-name":         it.get("productName") or "",
            "condition":            it.get("condition") or "",
            "your-price":           "",
            "mfn-listing-exists":   "No",
            "mfn-fulfillable-quantity": "",
            "afn-listing-exists":   _bool_yesno(True),
            "afn-warehouse-quantity":       warehouse,
            "afn-fulfillable-quantity":     fulfillable,
            "afn-unsellable-quantity":      unfulfillable,
            "afn-reserved-quantity":        reserved_qty,
            "afn-total-quantity":           total,
            "per-unit-volume":              "",
            "afn-inbound-working-quantity":   working,
            "afn-inbound-shipped-quantity":   shipped,
            "afn-inbound-receiving-quantity": receiving,
            "afn-researching-quantity":       researching,
            "afn-reserved-future-supply":     reserved_future,
            "afn-future-supply-buyable":      future_buyable,
            "store":                          "",
        })
    return rows


def run_account(acct: str) -> None:
    print(f"\n=== {acct} ===")
    tok = get_access_token(acct)
    items = fetch_all_summaries(tok)
    rows = summaries_to_rows(items)
    out_path = OUT_DIR / ACCOUNTS[acct]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    tot = sum(r["afn-total-quantity"] for r in rows)
    print(f"  wrote {len(rows)} SKUs, total afn-total sum={tot} -> {out_path.relative_to(REPO)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", choices=list(ACCOUNTS.keys()) + ["ALL"], default="ALL")
    args = ap.parse_args()

    load_dotenv(REPO / ".env")
    targets = list(ACCOUNTS.keys()) if args.account == "ALL" else [args.account]
    for acct in targets:
        run_account(acct)


if __name__ == "__main__":
    main()
