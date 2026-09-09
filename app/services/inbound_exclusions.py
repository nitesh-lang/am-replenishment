"""Dummy FBA inbound shipments to EXCLUDE from inbound math.

Operator 2026-09-09: shipments in data/input/inbound_exclusions.xlsx (drop
name: ExcludeAMPM_Checked_3P_23Aug-08Sep) are DUMMY shipments created on
Seller Central and OrderPilot for AMPM-check purposes — no stock will
actually arrive. Amazon still reports them in afn-inbound-* quantities and
in the inbound-shipments feed, so they INFLATE:
  - Replenishment's `inbound_inventory` (which nets down the ask via
    effective inventory), and
  - FC Allocation's `inbound_to_fc` (which nets down send_qty per FC).

Sheet columns: FBA Shipment ID, Account, Created via, Created, Dest FC,
Units, Status, OP Plan #. The sheet has NO SKU column — per-SKU quantities
come from joining the shipment IDs against the account's
inbound_shipments_<slug>.csv (SellerSKU rows).

Everything degrades safely: a missing/unreadable exclusions file means an
empty exclusion set, i.e. exactly the old behaviour.

To retire an exclusion (shipment cancelled/closed on SC): it disappears
from the --active-only inbound feed on its own, at which point the join
finds nothing and the exclusion is a natural no-op. The xlsx only needs
pruning for hygiene, not correctness.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parent.parent.parent
_FILE = _REPO / "data" / "input" / "inbound_exclusions.xlsx"

_INBOUND_CSVS = {
    "nexlev":      _REPO / "data" / "input" / "inbound_shipments_nexlev.csv",
    "viomi":       _REPO / "data" / "input" / "inbound_shipments_viomi.csv",
    "audio_array": _REPO / "data" / "input" / "inbound_shipments_audio_array.csv",
    "wm":          _REPO / "data" / "input" / "inbound_shipments_wm.csv",
}


def excluded_shipment_ids() -> set[str]:
    """All dummy shipment IDs from the exclusions sheet. Empty set on any
    problem — never let a bad exclusions file break the tabs."""
    try:
        df = pd.read_excel(_FILE)
        df.columns = [str(c).strip() for c in df.columns]
        col = next(c for c in df.columns if "shipment" in c.lower() and "id" in c.lower())
        return {s for s in df[col].astype(str).str.strip() if s and s.lower() != "nan"}
    except Exception as e:
        print(f"⚠️ inbound exclusions not loaded ({e}) — no exclusions applied")
        return set()


def excluded_units_by_sku(slugs: list[str]) -> dict[str, float]:
    """{SKU_upper: units_to_exclude} across the given inbound-file slugs.

    Units = QuantityShipped − QuantityReceived (clipped ≥0), RECEIVING rows
    skipped — mirroring exactly how fc_final_allocation counts inbound, so
    the subtraction can never exceed what was added.
    """
    ids = excluded_shipment_ids()
    if not ids:
        return {}
    out: dict[str, float] = {}
    for slug in slugs:
        p = _INBOUND_CSVS.get(slug)
        if p is None or not p.exists():
            continue
        try:
            b = pd.read_csv(p)
        except Exception:
            continue
        b = b[b["ShipmentId"].astype(str).str.strip().isin(ids)]
        if not len(b):
            continue
        b = b[b["ShipmentStatus"].astype(str).str.strip().str.upper() != "RECEIVING"]
        rem = (pd.to_numeric(b["QuantityShipped"], errors="coerce").fillna(0)
               - pd.to_numeric(b["QuantityReceived"], errors="coerce").fillna(0)).clip(lower=0)
        sku = b["SellerSKU"].astype(str).str.strip().str.upper()
        for s, u in zip(sku, rem):
            out[s] = out.get(s, 0) + float(u)
    return {k: v for k, v in out.items() if v > 0}
