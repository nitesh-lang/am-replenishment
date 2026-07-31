"""Internal PO service — powers the "PO Creation" tab.

Takes FC-wise send recommendations (from FC Allocation), splits into ONE
Internal PO per FC, generates INT-XXXXXXXX codes, stores locally in Neon
for draft/history, and forwards each PO to OrderPilot's ingest endpoint.

Design (per prompt_1_replenishment_tool.md):
- One brand can ship via multiple seller accounts, so the caller picks the
  selling_account at PO-creation time — never derived from brand here.
- Recommended qty is snapshotted per line so a later delta_vs_rec audit
  stays accurate even if the operator re-runs FC Allocation.
- INT-XXXXXXXX = 8-char base32 uppercase (32^8 ≈ 1 trillion — collision-
  retry on the tiny chance of a dupe).

Tables (created lazily; non-destructive):
  internal_po
    - po_id             SERIAL PRIMARY KEY
    - po_number         TEXT UNIQUE  ('INT-XXXXXXXX')
    - po_type           TEXT DEFAULT 'INTERNAL_PO'
    - selling_account_id TEXT
    - selling_account_name TEXT
    - ship_to_fc        TEXT
    - brand             TEXT
    - week_range        TEXT
    - cover             INT
    - poc               TEXT
    - created_by        TEXT
    - created_at        TIMESTAMPTZ  DEFAULT NOW()
    - status            TEXT DEFAULT 'PENDING_VERIFICATION'
    - orderpilot_status TEXT   ('ACKED', 'FAILED', 'PENDING', 'SKIPPED')
    - orderpilot_error  TEXT
    - is_draft          BOOLEAN DEFAULT FALSE
  internal_po_line
    - line_id           SERIAL PRIMARY KEY
    - po_id             INT REFERENCES internal_po(po_id) ON DELETE CASCADE
    - sku               TEXT
    - asin              TEXT
    - model             TEXT
    - recommended_qty   INT
    - quantity_requested INT
    - delta_vs_rec      INT
"""
from __future__ import annotations

import os
import random
import string
import time
from typing import Any

import requests

from app.services.db import get_conn


BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"  # RFC 4648 base32, uppercase

# In-repo mapping of env-key to human name. Order defines dropdown order.
# Reading strictly from .env (no hardcoded credentials — just names of
# accounts we know we have refresh_tokens for).
SELLING_ACCOUNTS_META = [
    ("NEXLEV",         "Nexlev"),
    ("VIOMI",          "Viomi"),
    ("AUDIOARRAY",     "Audio Array"),
    ("WHITEMULBERRY",  "White Mulberry"),
    ("CAMBIUMRETAIL",  "Cambium Retail"),
]


def _ensure_tables() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS internal_po (
                    po_id                SERIAL PRIMARY KEY,
                    po_number            TEXT UNIQUE NOT NULL,
                    po_type              TEXT DEFAULT 'INTERNAL_PO',
                    selling_account_id   TEXT,
                    selling_account_name TEXT,
                    ship_to_fc           TEXT,
                    brand                TEXT,
                    week_range           TEXT,
                    cover                INT,
                    poc                  TEXT,
                    created_by           TEXT,
                    created_at           TIMESTAMPTZ DEFAULT NOW(),
                    status               TEXT DEFAULT 'PENDING_VERIFICATION',
                    orderpilot_status    TEXT DEFAULT 'PENDING',
                    orderpilot_error     TEXT DEFAULT '',
                    is_draft             BOOLEAN DEFAULT FALSE
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS internal_po_line (
                    line_id              SERIAL PRIMARY KEY,
                    po_id                INT REFERENCES internal_po(po_id) ON DELETE CASCADE,
                    sku                  TEXT,
                    asin                 TEXT,
                    model                TEXT,
                    recommended_qty      INT DEFAULT 0,
                    quantity_requested   INT DEFAULT 0,
                    delta_vs_rec         INT DEFAULT 0
                )
            """)
        conn.commit()


def list_selling_accounts() -> list[dict]:
    """Return connected 3P seller accounts derived from stored SP-API
    refresh_tokens. Only accounts with a live SP_REFRESH_TOKEN_<KEY> in .env
    appear — matches the "no hardcode" rule in the spec.
    """
    out = []
    for env_key, human_name in SELLING_ACCOUNTS_META:
        if os.environ.get(f"SP_REFRESH_TOKEN_{env_key}"):
            out.append({"id": env_key, "name": human_name})
    return out


def generate_po_number() -> str:
    """INT-XXXXXXXX where X is base32 uppercase."""
    tail = "".join(random.choice(BASE32_ALPHABET) for _ in range(8))
    return f"INT-{tail}"


def _new_unique_po_number(cur, retries: int = 5) -> str:
    for _ in range(retries):
        candidate = generate_po_number()
        cur.execute("SELECT 1 FROM internal_po WHERE po_number = %s", (candidate,))
        if cur.fetchone() is None:
            return candidate
    # 32^8 ≈ 1 trillion — 5 collisions in a row means something's very wrong
    raise RuntimeError("Failed to generate unique INT PO number after 5 retries")


def create_internal_po(
    selling_account: dict,
    brand: str,
    week_range: str,
    cover: int,
    created_by: str,
    lines: list[dict],
    is_draft: bool = False,
) -> list[dict]:
    """Split lines FC-wise, create one Internal PO per FC, POST each to
    OrderPilot, and return summary rows.

    Args:
        selling_account: {"id": "...", "name": "..."} — from the dropdown.
        brand: e.g. "Nexlev"
        week_range: e.g. "Wk12-Wk30"
        cover: int weeks-of-cover parameter used
        created_by: BM name
        lines: [{ sku, asin, model, ship_to_fc, recommended_qty, quantity_requested }]
        is_draft: if True, skip OrderPilot POST and mark rows as draft

    Returns:
        [{ po_number, ship_to_fc, line_count, total_qty, orderpilot_status }]
    """
    if not selling_account or not selling_account.get("id"):
        raise ValueError("selling_account with id + name is required")
    if not lines:
        raise ValueError("At least one line is required")

    # Group by ship_to_fc
    by_fc: dict[str, list[dict]] = {}
    for ln in lines:
        fc = str(ln.get("ship_to_fc", "")).strip().upper()
        if not fc:
            continue
        req = int(ln.get("quantity_requested", 0) or 0)
        if req <= 0:
            continue  # spec: every included line has qty > 0
        by_fc.setdefault(fc, []).append(ln)

    if not by_fc:
        raise ValueError("No valid lines with ship_to_fc + quantity_requested > 0")

    _ensure_tables()
    orderpilot_url = os.environ.get("ORDERPILOT_BASE_URL", "").rstrip("/")
    poc = f"Replenishment · {created_by}" if created_by else "Replenishment"

    out: list[dict] = []
    with get_conn() as conn:
        for fc, fc_lines in by_fc.items():
            with conn.cursor() as cur:
                po_number = _new_unique_po_number(cur)
                cur.execute("""
                    INSERT INTO internal_po
                        (po_number, selling_account_id, selling_account_name,
                         ship_to_fc, brand, week_range, cover, poc, created_by,
                         is_draft, status, orderpilot_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING po_id
                """, (
                    po_number,
                    selling_account["id"], selling_account["name"],
                    fc, brand, week_range, int(cover or 0),
                    poc, created_by,
                    bool(is_draft),
                    "DRAFT" if is_draft else "PENDING_VERIFICATION",
                    "SKIPPED" if is_draft else "PENDING",
                ))
                po_id = cur.fetchone()[0]

                for ln in fc_lines:
                    rec  = int(ln.get("recommended_qty", 0) or 0)
                    req  = int(ln.get("quantity_requested", 0) or 0)
                    cur.execute("""
                        INSERT INTO internal_po_line
                            (po_id, sku, asin, model,
                             recommended_qty, quantity_requested, delta_vs_rec)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        po_id,
                        str(ln.get("sku", "")),
                        str(ln.get("asin", "")),
                        str(ln.get("model", "")),
                        rec, req, req - rec,
                    ))
            conn.commit()

            # POST to OrderPilot (unless draft or URL missing)
            op_status = "SKIPPED"
            op_error = ""
            if not is_draft and orderpilot_url:
                body = {
                    "po_type": "INTERNAL_PO",
                    "po_number": po_number,
                    "selling_account": {
                        "id":   selling_account["id"],
                        "name": selling_account["name"],
                    },
                    "ship_to_fc": fc,
                    "brand": brand,
                    "week_range": week_range,
                    "cover": int(cover or 0),
                    "poc": poc,
                    "created_by": created_by,
                    "status": "PENDING_VERIFICATION",
                    "lines": [
                        {
                            "sku": str(ln.get("sku", "")),
                            "asin": str(ln.get("asin", "")),
                            "model": str(ln.get("model", "")),
                            "recommended_qty": int(ln.get("recommended_qty", 0) or 0),
                            "quantity_requested": int(ln.get("quantity_requested", 0) or 0),
                            "delta_vs_rec": int(ln.get("quantity_requested", 0) or 0)
                                          - int(ln.get("recommended_qty", 0) or 0),
                        }
                        for ln in fc_lines
                    ],
                }
                try:
                    r = requests.post(
                        f"{orderpilot_url}/pos/ingest",
                        json=body,
                        timeout=30,
                    )
                    if r.status_code // 100 == 2:
                        op_status = "ACKED"
                    else:
                        op_status = "FAILED"
                        op_error = f"HTTP {r.status_code}: {r.text[:300]}"
                except Exception as e:
                    op_status = "FAILED"
                    op_error = str(e)[:300]

                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE internal_po
                        SET orderpilot_status = %s, orderpilot_error = %s
                        WHERE po_id = %s
                    """, (op_status, op_error, po_id))
                conn.commit()
            elif is_draft:
                op_status = "SKIPPED"
            else:
                op_status = "SKIPPED"
                op_error = "ORDERPILOT_BASE_URL not configured"
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE internal_po
                        SET orderpilot_status = %s, orderpilot_error = %s
                        WHERE po_id = %s
                    """, (op_status, op_error, po_id))
                conn.commit()

            out.append({
                "po_number": po_number,
                "ship_to_fc": fc,
                "line_count": len(fc_lines),
                "total_qty": sum(int(l.get("quantity_requested", 0) or 0) for l in fc_lines),
                "orderpilot_status": op_status,
                "orderpilot_error": op_error,
            })

    return out


def list_recent(limit: int = 50, drafts_only: bool = False) -> list[dict]:
    """Return recent Internal POs (header rows) for local history / draft
    listing. Line detail is fetched separately."""
    _ensure_tables()
    with get_conn() as conn:
        with conn.cursor() as cur:
            where = "WHERE is_draft = TRUE" if drafts_only else ""
            cur.execute(f"""
                SELECT po_id, po_number, selling_account_name, ship_to_fc,
                       brand, week_range, cover, poc, created_by, created_at,
                       status, orderpilot_status, orderpilot_error, is_draft
                FROM internal_po
                {where}
                ORDER BY created_at DESC
                LIMIT %s
            """, (int(limit),))
            rows = cur.fetchall()
    cols = ["po_id", "po_number", "selling_account_name", "ship_to_fc",
            "brand", "week_range", "cover", "poc", "created_by", "created_at",
            "status", "orderpilot_status", "orderpilot_error", "is_draft"]
    return [dict(zip(cols, r)) for r in rows]
