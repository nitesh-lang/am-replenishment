import json
from datetime import date

from app.services.db import get_conn


def ensure_table():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS replenishment_saved (
                    account       TEXT NOT NULL,
                    week_start    DATE NOT NULL,
                    sku           TEXT NOT NULL,
                    model         TEXT,
                    asin          TEXT,
                    working_value TEXT,
                    remarks       TEXT DEFAULT '',
                    snapshot      JSONB NOT NULL,
                    saved_at      TIMESTAMPTZ DEFAULT NOW(),
                    saved_by      TEXT,
                    PRIMARY KEY (account, week_start, sku)
                );
            """)
            # Idempotent add for pre-existing deployments
            cur.execute("ALTER TABLE replenishment_saved ADD COLUMN IF NOT EXISTS remarks TEXT DEFAULT '';")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_replen_saved_account_week
                ON replenishment_saved (account, week_start);
            """)
        conn.commit()


def save_rows(account: str, week_start: date, rows: list, saved_by: str) -> int:
    if not rows:
        return 0
    n = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for row in rows:
                sku = str(row.get("sku", "")).strip().upper()
                if not sku:
                    continue
                model = str(row.get("model", "") or "")
                asin = str(row.get("asin", "") or "")
                wv = row.get("working_value")
                working_value = "" if wv is None else str(wv)
                rk = row.get("remarks")
                remarks = "" if rk is None else str(rk)
                snapshot = json.dumps(row, default=str)
                cur.execute("""
                    INSERT INTO replenishment_saved
                        (account, week_start, sku, model, asin,
                         working_value, remarks, snapshot, saved_at, saved_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), %s)
                    ON CONFLICT (account, week_start, sku) DO UPDATE SET
                        model         = EXCLUDED.model,
                        asin          = EXCLUDED.asin,
                        working_value = EXCLUDED.working_value,
                        remarks       = EXCLUDED.remarks,
                        snapshot      = EXCLUDED.snapshot,
                        saved_at      = NOW(),
                        saved_by      = EXCLUDED.saved_by
                """, (account, week_start, sku, model, asin, working_value, remarks, snapshot, saved_by))
                n += 1
        conn.commit()
    return n


def load_working_value_map(account: str, week_start: date) -> dict:
    """For current week — load just the working_value + remarks by SKU.
    Returns {sku: {"working_value": str, "remarks": str}}."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT sku, working_value, remarks
                FROM replenishment_saved
                WHERE account = %s AND week_start = %s
            """, (account, week_start))
            return {
                sku: {"working_value": (wv or ""), "remarks": (rk or "")}
                for sku, wv, rk in cur.fetchall()
            }


def load_week_snapshot(account: str, week_start: date) -> list:
    """For past weeks — load full frozen snapshot. Each row includes
    working_value + remarks (both mutable across the week)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT snapshot, working_value, remarks, saved_at, saved_by
                FROM replenishment_saved
                WHERE account = %s AND week_start = %s
                ORDER BY sku
            """, (account, week_start))
            rows = []
            for snap, wv, rk, _, _ in cur.fetchall():
                if isinstance(snap, str):
                    snap = json.loads(snap)
                snap["working_value"] = wv or ""
                snap["remarks"] = rk or ""
                rows.append(snap)
            return rows


def list_saved_weeks(account: str) -> list:
    """Return [{week_start, saved_at}, ...] for an account, latest first."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT week_start, MAX(saved_at) AS last_saved
                FROM replenishment_saved
                WHERE account = %s
                GROUP BY week_start
                ORDER BY week_start DESC
            """, (account,))
            out = []
            for ws, sa in cur.fetchall():
                out.append({
                    "week_start": ws.isoformat() if isinstance(ws, date) else str(ws),
                    "saved_at":   sa.isoformat() if sa else None,
                })
            return out
