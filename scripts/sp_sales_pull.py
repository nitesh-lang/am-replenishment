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
import re
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

# SP-API returns kebab-case headers; manual Seller Central download uses
# Title Case. Downstream consumers (fc_planning.py etc.) expect the
# manual schema. Map explicitly so concatenation with older weekly files
# doesn't produce duplicate columns.
HEADER_MAP = {
    "amazon-order-id":            "Amazon Order Id",
    "merchant-order-id":          "Merchant Order Id",
    "shipment-id":                "Shipment ID",
    "shipment-item-id":           "Shipment Item Id",
    "amazon-order-item-id":       "Amazon Order Item Id",
    "merchant-order-item-id":     "Merchant Order Item Id",
    "purchase-date":              "Purchase Date",
    "payments-date":              "Payments Date",
    "shipment-date":              "Shipment Date",
    "reporting-date":             "Reporting Date",
    "buyer-email":                "Buyer Email",
    "buyer-name":                 "Buyer Name",
    "buyer-phone-number":         "Buyer Phone Number",
    "sku":                        "Merchant SKU",
    "product-name":               "Title",
    "quantity-shipped":           "Shipped Quantity",
    "currency":                   "Currency",
    "item-price":                 "Item Price",
    "item-tax":                   "Item Tax",
    "shipping-price":             "Shipping Price",
    "shipping-tax":               "Shipping Tax",
    "gift-wrap-price":            "Gift Wrap Price",
    "gift-wrap-tax":              "Gift Wrap Tax",
    "ship-service-level":         "Ship Service Level",
    "recipient-name":             "Recipient Name",
    "ship-address-1":             "Shipping Address 1",
    "ship-address-2":             "Shipping Address 2",
    "ship-address-3":             "Shipping Address 3",
    "ship-city":                  "Shipping City",
    "ship-state":                 "Shipping State",
    "ship-postal-code":           "Shipping Postal Code",
    "ship-country":               "Shipping Country Code",
    "ship-phone-number":          "Shipping Phone Number",
    "bill-address-1":             "Billing Address 1",
    "bill-address-2":             "Billing Address 2",
    "bill-address-3":             "Billing Address 3",
    "bill-city":                  "Billing City",
    "bill-state":                 "Billing State",
    # bill-postal-code + bill-country stay lowercase — matches manual
    "item-promotion-discount":    "Item Promo Discount",
    "ship-promotion-discount":    "Shipment Promo Discount",
    "carrier":                    "Carrier",
    "tracking-number":            "Tracking Number",
    "estimated-arrival-date":     "Estimated Arrival Date",
    "fulfillment-center-id":      "FC",
    "fulfillment-channel":        "Fulfillment Channel",
    "sales-channel":              "Sales Channel",
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


_ACCOUNT_MASTER = {
    "NEXLEV":         [("replenishment_master_nexlev.xlsx", None)],
    "VIOMI":          [("replenishment_master_viomi.xlsx",  None)],
    "AUDIOARRAY":     [("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "AA")],
    "WHITEMULBERRY":  [("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "WM")],
    # CAMBIUMRETAIL (Fossil) deliberately uses global sku_master only — per
    # operator directive 2026-07-27. Fossil Replenishment.xlsx has ~12 SKUs
    # not in global; those go unfiltered on purpose, since Fossil's own
    # master is the operator's planning list, not a broader catalog.
}


# FC/channel prefix on an otherwise identical SKU. Amazon reports the SKU
# the order actually shipped under (FBS…/FBO…), while sku_master carries the
# FBA… variant of the same product. Matching literally drops those rows.
# Same regex + semantics as app/services/ampm_history.py:74 — longest
# alternative first so FBAM isn't partially eaten by FBA.
_SKU_PREFIX_RE = re.compile(r"^(FBAM|FBA|FBM|FBK|FBP|FBS|FBO)", re.IGNORECASE)


def _sku_stem(s: str) -> str:
    """SKU with its FC prefix stripped, for prefix-insensitive matching."""
    return _SKU_PREFIX_RE.sub("", (s or "").strip().upper())


def _load_master_skus(account: str | None = None) -> set[str] | None:
    """Return the union of allowed FBA SKUs for the filter.

    - Always includes the global sku_master's FBA SKU column (catalog-wide).
    - Additionally includes the account's own replenishment master when
      `account` is given, so per-account SKUs missing from global sku_master
      don't get silently dropped (audit 2026-07-27: ~29 orphans across all
      accounts — 2 Nex/Vio, 13 AA, 0 WM, 12 Fossil).

    Returns None if BOTH sources fail (in which case caller skips the filter).
    """
    try:
        import pandas as pd
    except Exception as e:
        print(f"  ! pandas unavailable ({e}); skipping master-SKU filter")
        return None

    skus: set[str] = set()

    # Global sku_master
    try:
        sm = pd.read_excel(REPO / "data" / "input" / "sku_master.xlsx")
        sm.columns = sm.columns.str.strip()
        col = "FBA SKU" if "FBA SKU" in sm.columns else next(
            (c for c in sm.columns if str(c).strip().upper() in ("SKU", "MERCHANT SKU")), None
        )
        if col:
            skus |= set(sm[col].astype(str).str.strip().str.upper())
    except Exception as e:
        print(f"  ! sku_master load failed ({e}); trying per-account master only")

    # Per-account replenishment master
    if account and account.upper() in _ACCOUNT_MASTER:
        for fname, sheet in _ACCOUNT_MASTER[account.upper()]:
            path = REPO / "data" / "input" / fname
            try:
                own = pd.read_excel(path, sheet_name=sheet) if sheet else pd.read_excel(path)
                own.columns = own.columns.str.strip()
                col = next(
                    (c for c in own.columns if str(c).strip().upper() in ("SKU", "FBA SKU", "MERCHANT SKU")),
                    None,
                )
                if col:
                    own_skus = set(own[col].astype(str).str.strip().str.upper())
                    own_skus.discard("NAN"); own_skus.discard("")
                    added = own_skus - skus
                    skus |= own_skus
                    if added:
                        print(f"  + {len(added)} extra SKU(s) from {fname} ({account}) not in global sku_master")
            except Exception as e:
                print(f"  ! {account} master {fname} load failed ({e})")

    if not skus:
        print("  ! no master SKUs loaded from either source; skipping master-SKU filter")
        return None
    return skus


def tsv_to_csv(raw: bytes, out_path: Path, filter_master_skus: bool = True,
               account: str | None = None) -> tuple[int, int]:
    """Report is TSV; write to CSV.
    When filter_master_skus=True, keep only rows whose Merchant SKU is in
    the master SKU set (global sku_master ∪ per-account replenishment master).
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

    # Normalize headers to match the manual Seller Central download schema
    # (Title Case) so downstream code that concats these files with older
    # weekly drops doesn't see duplicate columns.
    header_raw = rows[0]
    header = [HEADER_MAP.get(h.strip().lower(), h) for h in header_raw]
    body   = rows[1:]

    kept, dropped = body, []
    if filter_master_skus:
        master_skus = _load_master_skus(account)
        if master_skus is not None:
            # After the rename, the SKU column is "Merchant SKU"
            sku_idx = next(
                (i for i, h in enumerate(header)
                 if h.strip().lower() in ("merchant sku", "sku", "seller sku")),
                None,
            )
            if sku_idx is not None:
                # Match on the literal SKU first, then on the prefix-stripped
                # stem, so FC/channel variants (FBS…/FBO…) of a master FBA…
                # SKU aren't dropped as "non-master". Empty stems are excluded
                # so a bare prefix can't match everything.
                master_stems = {st for st in (_sku_stem(s) for s in master_skus) if st}
                kept, dropped = [], []
                for r in body:
                    raw_sku = r[sku_idx].strip().upper() if len(r) > sku_idx else ""
                    if raw_sku and (raw_sku in master_skus
                                    or _sku_stem(raw_sku) in master_stems):
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
    kept, dropped = tsv_to_csv(raw, out_path, filter_master_skus=filter_master, account=acct)
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
