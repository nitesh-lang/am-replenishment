"""
SP-API Inbound Shipment Pull — Nexlev (amazon.in / EU region)
==============================================================

Uses Fulfillment Inbound API v0 (direct endpoints, not Reports API):
    GET /fba/inbound/v0/shipments                       (shipment list, paginated)
    GET /fba/inbound/v0/shipments/{shipmentId}/items    (per-SKU breakdown)

Output:
    data/input/inbound_shipments_nexlev.csv
        One row per (ShipmentId, SellerSKU) with destination FC + qty.

Required env vars in .env:
    SP_LWA_CLIENT_ID
    SP_LWA_CLIENT_SECRET
    SP_REFRESH_TOKEN_NEXLEV

Usage:
    python scripts/sp_inbound_pull.py
    python scripts/sp_inbound_pull.py --status WORKING,SHIPPED,IN_TRANSIT,RECEIVING
        (default = all active statuses; CLOSED+CANCELLED also fetched if no --status)
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import functools
from pathlib import Path

import requests
from dotenv import load_dotenv

# Force unbuffered stdout so progress shows in real time on Windows console
sys.stdout.reconfigure(line_buffering=True)
print = functools.partial(print, flush=True)

# ──────────────────────────────────────────────────────────────────────
LWA_URL        = "https://api.amazon.com/auth/o2/token"
SPAPI_HOST     = "https://sellingpartnerapi-eu.amazon.com"   # EU region (amazon.in)
MARKETPLACE_ID = "A21TJRUUN4KGV"                             # amazon.in

DEFAULT_STATUSES = (
    "WORKING,READY_TO_SHIP,SHIPPED,IN_TRANSIT,DELIVERED,CHECKED_IN,"
    "RECEIVING,CLOSED,CANCELLED,DELETED,ERROR"
)

# Polite throttle between shipment-items requests (SP-API rate limit)
PER_ITEM_DELAY = 0.5

REPO_ROOT  = Path(__file__).resolve().parent.parent

# Account → file slug (matches FC Allocation service)
ACCOUNT_SLUGS = {
    "nexlev":      "nexlev",
    "viomi":       "viomi",
    "audio_array": "audio_array",
    "wm":          "wm",
    "fossil":      "fossil",
}


def output_path(account: str) -> Path:
    slug = ACCOUNT_SLUGS.get(account, account.lower().replace(" ", "_"))
    return REPO_ROOT / "data" / "input" / f"inbound_shipments_{slug}.csv"


def get_access_token(account: str) -> str:
    """Per-account LWA credentials. Some accounts (e.g. Viomi) live under
    a different Amazon account and therefore have their own SP-API app
    with its own Client ID/Secret. Falls back to the default
    SP_LWA_CLIENT_ID / _SECRET if no per-account override is set."""
    acct_upper = account.upper()

    cid = os.environ.get(f"SP_LWA_CLIENT_ID_{acct_upper}")     or os.environ.get("SP_LWA_CLIENT_ID")
    sec = os.environ.get(f"SP_LWA_CLIENT_SECRET_{acct_upper}") or os.environ.get("SP_LWA_CLIENT_SECRET")
    rt  = os.environ.get(f"SP_REFRESH_TOKEN_{acct_upper}")

    if not rt:
        raise SystemExit(f"❌ Missing SP_REFRESH_TOKEN_{acct_upper} in .env")
    if not cid or not sec:
        raise SystemExit(f"❌ Missing LWA credentials. Provide either "
                         f"SP_LWA_CLIENT_ID_{acct_upper} + SP_LWA_CLIENT_SECRET_{acct_upper}, "
                         f"or the shared SP_LWA_CLIENT_ID + SP_LWA_CLIENT_SECRET.")

    r = requests.post(LWA_URL, data={
        "grant_type":    "refresh_token",
        "refresh_token": rt,
        "client_id":     cid,
        "client_secret": sec,
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def list_shipments(token: str, statuses: str, max_pages: int | None = None) -> list[dict]:
    """Page through every shipment matching the status list."""
    headers = {"x-amz-access-token": token}
    out = []
    next_token = None
    page = 0
    while True:
        page += 1
        if next_token:
            # On paged requests use QueryType=NEXT_TOKEN + NextToken + MarketplaceId
            # (the original ShipmentStatusList is encoded inside the token)
            params = {
                "QueryType":     "NEXT_TOKEN",
                "NextToken":     next_token,
                "MarketplaceId": MARKETPLACE_ID,
            }
        else:
            params = {
                "ShipmentStatusList": statuses,
                "QueryType":          "SHIPMENT",
                "MarketplaceId":      MARKETPLACE_ID,
            }
        r = requests.get(f"{SPAPI_HOST}/fba/inbound/v0/shipments",
                         params=params, headers=headers, timeout=30)
        if r.status_code == 429:
            print("  ! 429 throttled, waiting 5s")
            time.sleep(5); continue
        if r.status_code != 200:
            print(f"  ! HTTP {r.status_code}: {r.text[:400]}")
        r.raise_for_status()
        payload = r.json().get("payload", {}) or {}
        ships = payload.get("ShipmentData", []) or []
        print(f"  page {page}: {len(ships)} shipments")
        out.extend(ships)
        next_token = payload.get("NextToken")
        if not next_token:
            break
        if max_pages and page >= max_pages:
            print(f"  reached --max-pages={max_pages}, stopping")
            break
        time.sleep(PER_ITEM_DELAY)
    return out


def fetch_items(token: str, shipment_id: str) -> list[dict]:
    """Page through items of one shipment."""
    headers = {"x-amz-access-token": token}
    out = []
    next_token = None
    while True:
        if next_token:
            params = {"QueryType": "NEXT_TOKEN", "NextToken": next_token,
                      "MarketplaceId": MARKETPLACE_ID}
        else:
            params = {"MarketplaceId": MARKETPLACE_ID}
        r = requests.get(
            f"{SPAPI_HOST}/fba/inbound/v0/shipments/{shipment_id}/items",
            params=params, headers=headers, timeout=30,
        )
        if r.status_code == 429:
            time.sleep(5); continue
        if r.status_code != 200:
            print(f"  ! {shipment_id} items HTTP {r.status_code}: {r.text[:120]}")
            return out
        payload = r.json().get("payload", {}) or {}
        items = payload.get("ItemData", []) or []
        out.extend(items)
        next_token = payload.get("NextToken")
        if not next_token:
            break
        time.sleep(PER_ITEM_DELAY)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", default=DEFAULT_STATUSES,
                        help="Comma-separated shipment statuses (default: all)")
    parser.add_argument("--active-only", action="store_true",
                        help="Shortcut for the in-flight statuses only")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Stop after N pages (smoke test; default: all)")
    parser.add_argument("--account", default="nexlev",
                        choices=sorted(ACCOUNT_SLUGS.keys()),
                        help="Which seller account to pull (uses SP_REFRESH_TOKEN_<ACCOUNT>)")
    args = parser.parse_args()

    if args.active_only:
        statuses = "WORKING,READY_TO_SHIP,SHIPPED,IN_TRANSIT,DELIVERED,CHECKED_IN,RECEIVING"
    else:
        statuses = args.status

    load_dotenv(REPO_ROOT / ".env")
    for k in ("SP_LWA_CLIENT_ID", "SP_LWA_CLIENT_SECRET"):
        if not os.environ.get(k):
            print(f"❌ Missing env var: {k}"); sys.exit(1)

    print(f"→ Account: {args.account}")
    print("→ Getting LWA access token…")
    token = get_access_token(args.account)
    print("  OK\n")

    print(f"→ Listing shipments (status: {statuses[:60]}…)")
    ships = list_shipments(token, statuses, max_pages=args.max_pages)
    print(f"  Total: {len(ships)} shipments\n")

    if not ships:
        print("⚠ No shipments returned. Nothing to write.")
        return

    print(f"→ Fetching items for each shipment (this can take a minute)…")
    rows = []
    for i, s in enumerate(ships, 1):
        sid     = s.get("ShipmentId")
        sname   = s.get("ShipmentName", "")
        fc      = s.get("DestinationFulfillmentCenterId", "")
        status  = s.get("ShipmentStatus", "")
        addr    = s.get("ShipFromAddress", {}) or {}
        ship_from = f"{addr.get('City','')}, {addr.get('StateOrProvinceCode','')}".strip(", ")

        items = fetch_items(token, sid)
        if i % 10 == 0 or i == len(ships):
            print(f"  [{i:3d}/{len(ships)}] {sid:14s} {status:12s} {fc:6s} → {len(items)} items")
        for it in items:
            rows.append({
                "ShipmentId":      sid,
                "ShipmentName":    sname,
                "ShipmentStatus":  status,
                "DestinationFC":   fc,
                "ShipFrom":        ship_from,
                "SellerSKU":       it.get("SellerSKU", ""),
                "FNSKU":           it.get("FulfillmentNetworkSKU", ""),
                "QuantityShipped": it.get("QuantityShipped", 0),
                "QuantityReceived":it.get("QuantityReceived", 0),
                "QuantityInCase":  it.get("QuantityInCase", 0),
            })
        time.sleep(PER_ITEM_DELAY)

    out_csv = output_path(args.account)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    cols = ["ShipmentId", "ShipmentName", "ShipmentStatus", "DestinationFC",
            "ShipFrom", "SellerSKU", "FNSKU", "QuantityShipped",
            "QuantityReceived", "QuantityInCase"]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"\n✓ Wrote {len(rows)} rows from {len(ships)} shipments")
    print(f"  → {out_csv.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
