import os
import json
import psycopg2
from datetime import date


def _conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def ensure_table():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cb_replenishment_saved (
            week_start    DATE NOT NULL,
            model         TEXT NOT NULL,
            brand         TEXT,
            sku           TEXT,
            asin          TEXT,
            working_value TEXT,
            remarks       TEXT,
            snapshot      JSONB,
            saved_at      TIMESTAMPTZ DEFAULT NOW(),
            saved_by      TEXT,
            PRIMARY KEY (week_start, model)
        );
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cb_replen_saved_week
        ON cb_replenishment_saved (week_start);
    """)
    conn.commit()
    cur.close()
    conn.close()


def save_row(week_start: date, model: str, working_value, remarks, snapshot: dict, saved_by: str):
    conn = _conn()
    cur = conn.cursor()
    wv = "" if working_value is None else str(working_value)
    rk = "" if remarks is None else str(remarks)
    brand = str(snapshot.get("brand", "") or "")
    sku = str(snapshot.get("sku", "") or "")
    asin = str(snapshot.get("asin", "") or "")
    snap_json = json.dumps(snapshot, default=str)
    cur.execute("""
        INSERT INTO cb_replenishment_saved
            (week_start, model, brand, sku, asin, working_value, remarks, snapshot, saved_at, saved_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), %s)
        ON CONFLICT (week_start, model) DO UPDATE SET
            brand         = EXCLUDED.brand,
            sku           = EXCLUDED.sku,
            asin          = EXCLUDED.asin,
            working_value = EXCLUDED.working_value,
            remarks       = EXCLUDED.remarks,
            snapshot      = EXCLUDED.snapshot,
            saved_at      = NOW(),
            saved_by      = EXCLUDED.saved_by
    """, (week_start, model, brand, sku, asin, wv, rk, snap_json, saved_by))
    conn.commit()
    cur.close()
    conn.close()


def load_current_week_map(week_start: date) -> dict:
    """Map of model -> {working_value, remarks} for the given week."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT model, working_value, remarks
        FROM cb_replenishment_saved
        WHERE week_start = %s
    """, (week_start,))
    out = {}
    for model, wv, rk in cur.fetchall():
        out[model] = {"working_value": wv or "", "remarks": rk or ""}
    cur.close()
    conn.close()
    return out


def load_week_snapshot(week_start: date) -> list:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT snapshot, working_value, remarks
        FROM cb_replenishment_saved
        WHERE week_start = %s
        ORDER BY model
    """, (week_start,))
    rows = []
    for snap, wv, rk in cur.fetchall():
        if isinstance(snap, str):
            snap = json.loads(snap)
        snap = snap or {}
        snap["working_value"] = wv or ""
        snap["remarks"] = rk or ""
        rows.append(snap)
    cur.close()
    conn.close()
    return rows


def list_saved_weeks() -> list:
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT week_start, MAX(saved_at) AS last_saved
        FROM cb_replenishment_saved
        GROUP BY week_start
        ORDER BY week_start DESC
    """)
    out = []
    for ws, sa in cur.fetchall():
        out.append({
            "week_start": ws.isoformat() if isinstance(ws, date) else str(ws),
            "saved_at":   sa.isoformat() if sa else None,
        })
    cur.close()
    conn.close()
    return out
