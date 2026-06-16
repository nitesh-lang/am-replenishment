from fastapi import APIRouter, Query, Request
from app.services.inbound_shipments import load_inbound_shipments
from app.services.db import get_conn

router = APIRouter(prefix="", tags=["inbound-shipments"])


def _ensure_table():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS fba_inbound_remarks (
                    account     TEXT NOT NULL,
                    shipment_id TEXT NOT NULL,
                    seller_sku  TEXT NOT NULL,
                    remarks     TEXT DEFAULT '',
                    updated_at  TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (account, shipment_id, seller_sku)
                )
            """)
        conn.commit()


def _load_remarks(account: str) -> dict:
    """Return {(shipment_id, seller_sku): remarks} for the account."""
    try:
        _ensure_table()
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT shipment_id, seller_sku, remarks FROM fba_inbound_remarks WHERE account = %s",
                    (account.strip().upper(),),
                )
                rows = cur.fetchall()
        return {(r[0], r[1]): r[2] or "" for r in rows}
    except Exception as e:
        print(f"⚠️ fba_inbound_remarks load skipped: {e}")
        return {}


@router.get("/inbound-shipments")
def get_inbound_shipments(account: str = Query(default="NEXLEV")):
    df = load_inbound_shipments(account)
    if df.empty:
        return {"account": account, "rows": [], "summary": {}}

    df = df.fillna("")
    remarks_map = _load_remarks(account)
    records = df.to_dict(orient="records")
    for r in records:
        key = (str(r.get("ShipmentId", "")), str(r.get("SellerSKU", "")))
        r["Remarks"] = remarks_map.get(key, "")

    in_flight_statuses = {"WORKING", "READY_TO_SHIP", "SHIPPED", "IN_TRANSIT"}
    at_fc_statuses     = {"DELIVERED", "CHECKED_IN", "RECEIVING"}

    summary = {
        "total_rows":      len(records),
        "total_shipments": df["ShipmentId"].nunique(),
        "in_flight_units": int(df[df["ShipmentStatus"].isin(in_flight_statuses)]["QuantityShipped"].sum()),
        "at_fc_remaining": int((df[df["ShipmentStatus"].isin(at_fc_statuses)]["QuantityShipped"]
                                - df[df["ShipmentStatus"].isin(at_fc_statuses)]["QuantityReceived"])
                               .clip(lower=0).sum()),
    }
    summary["total_incoming"] = summary["in_flight_units"] + summary["at_fc_remaining"]

    return {"account": account, "rows": records, "summary": summary}


@router.post("/inbound-shipments/save-remarks")
async def save_remarks(request: Request):
    """Upsert one or many {shipment_id, seller_sku, remarks} rows for the account."""
    try:
        body = await request.json()
        account = str(body.get("account", "NEXLEV")).strip().upper()
        rows = body.get("rows") or []
        if isinstance(rows, dict):
            rows = [rows]

        _ensure_table()
        with get_conn() as conn:
            with conn.cursor() as cur:
                for r in rows:
                    sid     = str(r.get("shipment_id", "")).strip()
                    sku     = str(r.get("seller_sku", "")).strip().upper()
                    remarks = str(r.get("remarks", ""))
                    if not sid or not sku:
                        continue
                    cur.execute(
                        """
                        INSERT INTO fba_inbound_remarks (account, shipment_id, seller_sku, remarks, updated_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        ON CONFLICT (account, shipment_id, seller_sku)
                        DO UPDATE SET remarks = EXCLUDED.remarks, updated_at = NOW()
                        """,
                        (account, sid, sku, remarks),
                    )
            conn.commit()
        return {"status": "saved", "rows": len(rows)}
    except Exception as e:
        print(f"⚠️ fba_inbound_remarks save error: {e}")
        return {"status": "error", "error": str(e)}
