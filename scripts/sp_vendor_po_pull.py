"""
SP-API Vendor Purchase Orders Status Pull (CRPL — AA + Tonor)
=============================================================

Uses `/vendor/orders/v1/purchaseOrdersStatus` (richer than purchaseOrders)
so we get the same fields the Vendor Central UI shows:

    confirmationStatus   == ACCEPTED         -> "AC - Accepted: In stock"
    acceptedQuantity.amount                  -> "Accepted quantity"
    receivedQuantity.amount  (0 if absent)   -> "Received quantity"
    acceptedQuantity - receivedQuantity      -> "Remaining quantity" (in-transit)
    rejectedQuantity.amount                  -> "Cancelled quantity"
    purchaseOrderStatus  == OPEN             -> in-flight PO
    shipToParty.partyId                      -> "Ship-to location" (FC)

Filter applied to output:
    confirmationStatus == ACCEPTED  AND  Remaining quantity > 0

That gives the same "live in-transit" view as the VC POItemExport
filtered to (Availability='AC - Accepted: In stock' & Remaining qty > 0).

Output:
    data/input/vendor_po_audio_array.csv
    data/input/vendor_po_tonor.csv
    data/input/vendor_po_unmatched_audioarray.csv  (ASINs not in sku_master)

Required env (.env):
    SP_API_VENDOR_REFRESH_TOKEN_AUDIOARRAY   (CRPL cb — covers AA + Tonor)
    SP_LWA_CLIENT_ID_AUDIOARRAY              (AdPilot Production)
    SP_LWA_CLIENT_SECRET_AUDIOARRAY

Usage:
    python scripts/sp_vendor_po_pull.py            # 180 days back
    python scripts/sp_vendor_po_pull.py --days 365
"""
from __future__ import annotations

import argparse
import functools
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
REPO_ROOT  = Path(__file__).resolve().parent.parent

BRAND_OUTPUTS = {
    "Audio Array": REPO_ROOT / "data" / "input" / "vendor_po_audio_array.csv",
    "Tonor":       REPO_ROOT / "data" / "input" / "vendor_po_tonor.csv",
}

OUT_COLS = [
    "PO", "Order date", "Last updated", "PO Status",
    "Confirmation Status",
    "Ship-to location",
    "ASIN", "SKU", "Model", "Brand",
    "Accepted quantity", "Received quantity", "Remaining quantity",
    "Cancelled quantity",
    "Cost", "Currency", "Total accepted cost", "Total remaining cost",
    "Receive Status",
]


def get_access_token() -> str:
    acct = "AUDIOARRAY"
    cid = os.environ.get(f"SP_LWA_CLIENT_ID_{acct}")     or os.environ.get("SP_LWA_CLIENT_ID")
    sec = os.environ.get(f"SP_LWA_CLIENT_SECRET_{acct}") or os.environ.get("SP_LWA_CLIENT_SECRET")
    rt  = os.environ.get(f"SP_API_VENDOR_REFRESH_TOKEN_{acct}")
    if not (cid and sec and rt):
        raise SystemExit(f"Missing LWA creds or SP_API_VENDOR_REFRESH_TOKEN_{acct} in .env")
    r = requests.post(LWA_URL, data={
        "grant_type": "refresh_token", "refresh_token": rt,
        "client_id": cid, "client_secret": sec,
    }, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"LWA failed: HTTP {r.status_code} {r.text[:300]}")
    return r.json()["access_token"]


def _amt(obj: dict | None) -> float:
    """Pull `.amount` from {amount, unitOfMeasure, unitSize} dict, default 0."""
    if not obj or not isinstance(obj, dict):
        return 0.0
    try:
        return float(obj.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def pull_po_status(token: str, days: int) -> list[dict]:
    headers = {"x-amz-access-token": token}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end   = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"  window: {start} -> {end}")
    out = []
    next_token = None
    page = 0
    while True:
        page += 1
        params = {
            "createdAfter": start,
            "createdBefore": end,
            "limit": 100,
            "sortOrder": "DESC",
        }
        if next_token:
            params["nextToken"] = next_token
        r = requests.get(
            f"{SPAPI_HOST}/vendor/orders/v1/purchaseOrdersStatus",
            params=params, headers=headers, timeout=30,
        )
        if r.status_code == 429:
            print("  429 throttled, sleeping 10s")
            time.sleep(10); continue
        if r.status_code != 200:
            print(f"  HTTP {r.status_code}: {r.text[:300]}")
            r.raise_for_status()
        payload = r.json().get("payload", {})
        orders = payload.get("ordersStatus", []) or []
        out.extend(orders)
        next_token = payload.get("pagination", {}).get("nextToken")
        print(f"  page {page}: {len(orders)} POs  (running total {len(out)})")
        if not next_token:
            break
        time.sleep(0.5)
    return out


def flatten(orders: list[dict]) -> pd.DataFrame:
    rows = []
    for po in orders:
        po_num     = po.get("purchaseOrderNumber", "")
        po_status  = po.get("purchaseOrderStatus", "")  # OPEN / CLOSED
        po_date    = po.get("purchaseOrderDate", "")
        last_upd   = po.get("lastUpdatedDate", "")
        ship_to    = (po.get("shipToParty") or {}).get("partyId", "")

        for it in (po.get("itemStatus") or []):
            asin       = it.get("buyerProductIdentifier", "")
            cost_obj   = it.get("netCost") or {}
            unit_cost  = cost_obj.get("amount")
            currency   = cost_obj.get("currencyCode", "")

            ack_obj  = it.get("acknowledgementStatus") or {}
            conf     = ack_obj.get("confirmationStatus", "")
            accepted = int(_amt(ack_obj.get("acceptedQuantity")))
            rejected = int(_amt(ack_obj.get("rejectedQuantity")))

            recv_obj  = it.get("receivingStatus") or {}
            recv_st   = recv_obj.get("receiveStatus", "")
            received  = int(_amt(recv_obj.get("receivedQuantity")))

            remaining = max(0, accepted - received)
            try:
                total_acc  = float(unit_cost) * accepted  if unit_cost not in (None, "") else None
                total_rem  = float(unit_cost) * remaining if unit_cost not in (None, "") else None
            except (TypeError, ValueError):
                total_acc, total_rem = None, None

            rows.append({
                "PO":                  po_num,
                "Order date":          po_date,
                "Last updated":        last_upd,
                "PO Status":           po_status,
                "Confirmation Status": conf,
                "Ship-to location":    ship_to,
                "ASIN":                asin,
                "Accepted quantity":   accepted,
                "Received quantity":   received,
                "Remaining quantity":  remaining,
                "Cancelled quantity":  rejected,
                "Cost":                unit_cost,
                "Currency":            currency,
                "Total accepted cost": total_acc,
                "Total remaining cost": total_rem,
                "Receive Status":      recv_st,
            })
    return pd.DataFrame(rows)


def annotate_with_master(df: pd.DataFrame) -> pd.DataFrame:
    sm_path = REPO_ROOT / "data" / "input" / "sku_master.xlsx"
    if df.empty or not sm_path.exists():
        df["SKU"] = ""
        df["Model"] = ""
        df["Brand"] = ""
        return df
    sm = pd.read_excel(sm_path)
    sm.columns = sm.columns.str.strip()
    sm["ASIN"] = sm["ASIN"].astype(str).str.strip().str.upper()
    sm = sm[["ASIN", "FBA SKU", "Brand", "Model"]].drop_duplicates("ASIN", keep="first")
    sm = sm.rename(columns={"FBA SKU": "SKU"})
    df["ASIN"] = df["ASIN"].astype(str).str.strip().str.upper()
    return df.merge(sm, on="ASIN", how="left")


def write_brand_csv(df: pd.DataFrame, brand: str, out_path: Path) -> int:
    sub = df[df["Brand"].astype(str).str.strip().str.lower() == brand.lower()].copy()
    for c in OUT_COLS:
        if c not in sub.columns:
            sub[c] = ""
    sub = sub[OUT_COLS]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sub.to_csv(out_path, index=False)
    accepted  = int(pd.to_numeric(sub["Accepted quantity"], errors="coerce").fillna(0).sum())
    remaining = int(pd.to_numeric(sub["Remaining quantity"], errors="coerce").fillna(0).sum())
    print(f"  -> {out_path.relative_to(REPO_ROOT)}  "
          f"({len(sub)} rows, accepted={accepted}, remaining/in-transit={remaining})")
    return len(sub)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    args = ap.parse_args()
    load_dotenv(REPO_ROOT / ".env")

    print(f"-> CRPL cb vendor token (covers AA + Tonor); look back {args.days} days")
    tok = get_access_token()
    print("  auth OK")

    print("-> fetching purchase orders status …")
    orders = pull_po_status(tok, args.days)
    print(f"  POs pulled: {len(orders)}")

    df = flatten(orders)
    print(f"  PO line items: {len(df)}")

    # Filter: ACCEPTED items still in-transit (Remaining > 0)
    # That mirrors VC export filter: Availability='AC - Accepted: In stock' & Remaining > 0
    df = df[(df["Confirmation Status"] == "ACCEPTED") & (df["Remaining quantity"] > 0)].copy()
    print(f"  after ACCEPTED + Remaining>0 filter: {len(df)} line items")

    df = annotate_with_master(df)
    present = df["Brand"].astype(str).str.strip().value_counts().to_dict()
    print(f"  brand split (per sku_master): {present}")

    for brand, out_path in BRAND_OUTPUTS.items():
        write_brand_csv(df, brand, out_path)

    unm = df[df["Brand"].isna() | (df["Brand"].astype(str).str.lower().isin(["nan", ""]))].copy()
    if not unm.empty:
        unm_path = REPO_ROOT / "data" / "input" / "vendor_po_unmatched_audioarray.csv"
        for c in OUT_COLS:
            if c not in unm.columns:
                unm[c] = ""
        unm[OUT_COLS].to_csv(unm_path, index=False)
        print(f"  ! {len(unm)} ASINs missing from sku_master -> {unm_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
