"""
Inbound Shipments service — Nexlev only (for now).

Reads data/input/inbound_shipments_nexlev.csv (produced by
scripts/sp_inbound_pull.py) and enriches each row with ASIN + Model
from sku_master.xlsx via SellerSKU lookup.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from app.services.file_cache import get


def load_inbound_shipments(account: str = "NEXLEV") -> pd.DataFrame:
    """Return enriched inbound-shipments DataFrame for the given account.

    Output columns:
        SellerSKU, ASIN, Model, ShipFrom, DestinationFC,
        QuantityShipped, QuantityReceived, QuantityInCase, ShipmentStatus,
        ShipmentId, ShipmentName
    """
    acct = account.strip().upper()
    fname_map = {
        "NEXLEV": "inbound_shipments_nexlev.csv",
        "VIOMI":  "inbound_shipments_viomi.csv",
    }
    fname = fname_map.get(acct)
    if not fname:
        return pd.DataFrame()

    try:
        df = get(fname)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["SellerSKU"] = df["SellerSKU"].astype(str).str.strip().str.upper()

    # ── ASIN + Model lookup from sku_master ──
    try:
        sm = get("sku_master.xlsx")
        sm = sm.copy()
        sm.columns = sm.columns.str.strip()
        sm = sm.dropna(subset=["FBA SKU"]).copy()
        sm["_sku"] = sm["FBA SKU"].astype(str).str.strip().str.upper()
        sm = sm.drop_duplicates(subset=["_sku"], keep="first")
        lookup = sm.set_index("_sku")[["ASIN", "Model"]]
        df = df.merge(
            lookup,
            how="left",
            left_on="SellerSKU",
            right_index=True,
            suffixes=("", "_master"),
        )
        # If the CSV already has an ASIN/FNSKU, prefer the master's authoritative ASIN
        # when present (it can override variant-vs-parent drift), but fall back to
        # the shipment CSV value where master is missing.
        if "ASIN_master" in df.columns:
            df["ASIN"] = df["ASIN_master"].fillna(df.get("ASIN", ""))
            df = df.drop(columns=["ASIN_master"])
    except Exception as e:
        print(f"⚠️ inbound_shipments: sku_master lookup failed: {e}")
        df["ASIN"] = df.get("ASIN", "")
        df["Model"] = ""

    df["ASIN"] = df["ASIN"].fillna("").astype(str)
    df["Model"] = df["Model"].fillna("").astype(str)

    for c in ("QuantityShipped", "QuantityReceived", "QuantityInCase"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    keep = [
        "ShipmentId", "ShipmentName", "ShipmentStatus",
        "ShipFrom", "DestinationFC",
        "SellerSKU", "ASIN", "Model",
        "QuantityShipped", "QuantityReceived", "QuantityInCase",
    ]
    for c in keep:
        if c not in df.columns:
            df[c] = ""
    return df[keep]
