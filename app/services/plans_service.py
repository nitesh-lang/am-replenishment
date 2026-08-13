"""
Plan lifecycle for FC Allocation approvals.

Naresh (plans-editor) proposes a plan by snapshotting current FC Allocation
rows into a plan_batch. Sagar (plans-approver) can freely edit qty,
delete rows, add new (SKU x FC) rows, then approve. Approval flips state
to "approved"; the actual push to OrderPilot's /api/inbound-plans is
gated behind push_plan() which is currently a STUB — we build the whole
lifecycle first, wire the push only after both apps have coordinated.

Tables:
  plan_batches       — one row per proposal (account, week_tag, status,
                       proposed_by/at, approved_by/at, pushed_at, err)
  plan_lines         — line items in the batch; soft-deletable; carries
                       added_by/edited_by badges + original_send_qty audit
  plan_line_events   — append-only audit log (add/edit/delete/undelete)

Status flow:
  draft    -> proposed  (Naresh's "Send to Approver" action; drafts are
                         editor-editable snapshots)
  proposed -> approved  (assigned approver's "Approve" action)
  approved -> pushed    (push_plan STUB; not shipped yet)
  approved -> failed    (retry available)

Edit permissions:
  status='draft'    — only the proposer (or admin) can edit lines
  status='proposed' — only the assigned approver (or admin) can edit lines
  status='approved' or later — nobody can edit (create a new batch instead)
"""

import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any

import psycopg2
import requests
from psycopg2.extras import RealDictCursor

from app.services.db import get_conn


# Cache for AA CB SOH lookup used by get_batch backfill. CB Rep load is
# expensive (Excel + DB overlay); cache for 5 min so a burst of GETs
# doesn't hammer it. Cleared naturally on process restart.
_CB_SOH_CACHE: dict = {"map": None, "ts": 0.0}
_CB_SOH_TTL_SEC = 300


def _cached_cb_soh_map():
    now = time.time()
    if _CB_SOH_CACHE["map"] is not None and (now - _CB_SOH_CACHE["ts"]) < _CB_SOH_TTL_SEC:
        return _CB_SOH_CACHE["map"]
    try:
        from app.services.replenishment import _cb_soh_by_model
        m = _cb_soh_by_model("Audio Array") or {}
    except Exception as e:
        print(f"⚠️ CB SOH cache refresh failed: {e}")
        m = _CB_SOH_CACHE["map"] or {}  # keep stale value on failure
    _CB_SOH_CACHE["map"] = m
    _CB_SOH_CACHE["ts"] = now
    return m


# ============================================================
# SCHEMA
# ============================================================
_DDL = """
CREATE TABLE IF NOT EXISTS plan_batches (
    batch_id        TEXT PRIMARY KEY,
    account         TEXT NOT NULL,
    source_module   TEXT,                 -- 'fc-allocation' | 'fossil-replenishment' | ...
    approver_email  TEXT,                 -- if set, only this user (or admin) can approve
    week_tag        TEXT,
    status          TEXT NOT NULL DEFAULT 'proposed',
    proposed_by     TEXT NOT NULL,
    proposed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_by     TEXT,
    approved_at     TIMESTAMPTZ,
    pushed_at       TIMESTAMPTZ,
    push_error      TEXT,
    parent_batch_id TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Add columns idempotently for pre-existing deployments
ALTER TABLE plan_batches ADD COLUMN IF NOT EXISTS source_module     TEXT;
ALTER TABLE plan_batches ADD COLUMN IF NOT EXISTS approver_email    TEXT;
ALTER TABLE plan_batches ADD COLUMN IF NOT EXISTS cover_weeks       INT;
ALTER TABLE plan_batches ADD COLUMN IF NOT EXISTS approver_feedback TEXT;
ALTER TABLE plan_lines   ADD COLUMN IF NOT EXISTS real_am_inv       INT;
ALTER TABLE plan_lines   ADD COLUMN IF NOT EXISTS mother_inv        INT;
ALTER TABLE plan_lines   ADD COLUMN IF NOT EXISTS weekly_velocity   NUMERIC(10,2);
-- Cambium vendor warehouse stock at propose time — AA-only for now
-- (sourced from CB Replenishment.final_cb_qty per model). NULL on
-- accounts without 1P vendor inventory so the approver column renders "—".
ALTER TABLE plan_lines   ADD COLUMN IF NOT EXISTS cb_soh            INT;
-- Amazon FBA rejects mixed shipments — OrderPilot must split each per-FC
-- group into 4 buckets (Hazmat × IXD). AM_Replen snapshots these flags
-- per line at propose time so the split key travels with the payload.
ALTER TABLE plan_lines   ADD COLUMN IF NOT EXISTS hazmat            BOOLEAN;
ALTER TABLE plan_lines   ADD COLUMN IF NOT EXISTS ixd_flag          TEXT;
-- Approver's reason for changing qty (Sagar/Kanwal explaining edits so
-- Naresh sees WHY). Separate from `notes` which is Naresh's remark.
ALTER TABLE plan_lines   ADD COLUMN IF NOT EXISTS approver_note     TEXT;
-- Approver toggle: keep the line in the batch (audit + visibility) but
-- SKIP it when pushing to OrderPilot. Used for stock at non-default
-- warehouses (e.g. MR-01 at Turbhe) that need their own dispatch flow.
ALTER TABLE plan_lines   ADD COLUMN IF NOT EXISTS exclude_from_push BOOLEAN NOT NULL DEFAULT FALSE;
-- Snapshot of the filter/selector state Naresh had when he proposed:
-- channel, sales-window from/to week, view filter, replenish_weeks cover.
-- Approver renders these as chips so they know what generated the plan.
ALTER TABLE plan_batches ADD COLUMN IF NOT EXISTS filter_context    JSONB;

CREATE INDEX IF NOT EXISTS idx_plan_batches_account_status
    ON plan_batches (account, status);

CREATE TABLE IF NOT EXISTS plan_lines (
    id                  BIGSERIAL PRIMARY KEY,
    batch_id            TEXT NOT NULL REFERENCES plan_batches (batch_id) ON DELETE CASCADE,
    sku                 TEXT NOT NULL,
    model               TEXT,
    asin                TEXT,
    destination_fc      TEXT NOT NULL,
    ship_from_wh        TEXT,
    qty                 INTEGER NOT NULL DEFAULT 0,
    original_send_qty   INTEGER NOT NULL DEFAULT 0,
    added_by            TEXT NOT NULL,
    edited_by           TEXT,
    last_edited_at      TIMESTAMPTZ,
    is_deleted          BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_by          TEXT,
    row_version         INTEGER NOT NULL DEFAULT 1,
    notes               TEXT,
    orderpilot_shipment_id TEXT,
    pushed_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plan_lines_batch
    ON plan_lines (batch_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_plan_lines_batch_sku_fc
    ON plan_lines (batch_id, sku, destination_fc);

CREATE TABLE IF NOT EXISTS plan_line_events (
    id            BIGSERIAL PRIMARY KEY,
    batch_id      TEXT NOT NULL,
    line_id       BIGINT,
    event_type    TEXT NOT NULL,         -- add | edit_qty | delete | undelete | approve | push | error
    actor         TEXT NOT NULL,
    payload_json  JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_plan_line_events_batch
    ON plan_line_events (batch_id, created_at DESC);
"""


def ensure_plans_tables() -> None:
    """Idempotent table create. Call once at app startup."""
    if not os.environ.get("DATABASE_URL"):
        # DB not configured — services degrade gracefully; caller decides.
        print("WARN: plans_service.ensure_plans_tables — DATABASE_URL not set, skipping")
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_DDL)
        conn.commit()


# ============================================================
# BATCH LIFECYCLE
# ============================================================
def _new_batch_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"pb_{stamp}_{secrets.token_hex(3)}"


def propose_plan(
    account: str,
    proposed_by: str,
    week_tag: str | None,
    rows: list[dict],
    source_module: str | None = None,
    approver_email: str | None = None,
    as_draft: bool = False,
    cover_weeks: int | None = None,
    filter_context: dict | None = None,
) -> str:
    """Snapshot the caller-provided rows into a new batch.

    `rows` is expected to be the current FC Allocation / Fossil
    Replenishment output for the account, filtered to `send_qty > 0`.
    Each row must have at minimum: sku, destination_fc, qty (int), and
    optionally model / asin / ship_from_wh / original_send_qty.

    Optional targeting:
      source_module   — the tab that originated the plan ('fc-allocation',
                        'fossil-replenishment', ...) so the approver UI can
                        show context.
      approver_email  — if set, only this user (or an admin) can approve
                        the batch. Naresh proposes from FC Allocation →
                        target Sagar; Naresh proposes from Fossil
                        Replenishment → target Kanwal.

    Returns the new batch_id.
    """
    account = (account or "").strip()
    proposed_by = (proposed_by or "").strip().lower()
    approver_email = (approver_email or "").strip().lower() or None
    source_module = (source_module or "").strip() or None
    if not account or not proposed_by:
        raise ValueError("account and proposed_by are required")
    if not rows:
        raise ValueError("no rows to propose")

    batch_id = _new_batch_id()
    initial_status = "draft" if as_draft else "proposed"

    def _int_or_none(v):
        if v is None or v == "": return None
        try: return int(round(float(v)))
        except (TypeError, ValueError): return None

    def _float_or_none(v):
        if v is None or v == "": return None
        try: return float(v)
        except (TypeError, ValueError): return None

    with get_conn() as conn:
        with conn.cursor() as cur:
            fc_json = json.dumps(filter_context) if isinstance(filter_context, dict) and filter_context else None
            cur.execute(
                """
                INSERT INTO plan_batches
                    (batch_id, account, source_module, approver_email,
                     week_tag, cover_weeks, filter_context, status, proposed_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                """,
                (batch_id, account, source_module, approver_email, week_tag,
                 _int_or_none(cover_weeks), fc_json, initial_status, proposed_by),
            )
            for r in rows:
                sku = str(r.get("sku", "")).strip().upper()
                fc  = str(r.get("destination_fc") or r.get("fulfillment_center") or "").strip().upper()
                qty = int(round(float(r.get("qty") or r.get("send_qty") or 0)))
                if not sku or not fc:
                    continue
                # Zero-qty rows are kept ONLY when the caller included a
                # non-empty note — Naresh may have looked at a SKU, set
                # Working=0/blank on purpose, and left a remark explaining
                # why. Approver needs to see that row + note.
                _notes = str(r.get("notes") or "").strip()
                if qty <= 0 and not _notes:
                    continue
                # Hazmat / IXD split keys — bool + text. Frontend may
                # send booleans or strings; normalize here.
                hz_raw = r.get("hazmat")
                if isinstance(hz_raw, bool):
                    hazmat = hz_raw
                elif hz_raw is None or hz_raw == "":
                    hazmat = None
                else:
                    hazmat = "hazmat" in str(hz_raw).lower() and "non" not in str(hz_raw).lower()
                ixd_raw = str(r.get("ixd_flag") or "").strip().upper()
                # Canonicalize to "IXD" / "NON IXD" / None. "NON IXD Hazmat" → "NON IXD"
                if not ixd_raw:
                    ixd_flag = None
                elif "NON IXD" in ixd_raw or "NON-IXD" in ixd_raw:
                    ixd_flag = "NON IXD"
                elif "IXD" in ixd_raw:
                    ixd_flag = "IXD"
                else:
                    ixd_flag = ixd_raw  # keep as-is if unrecognized

                # If caller sent original_send_qty explicitly (Replenishment
                # tab does this to preserve the calc engine's suggestion),
                # respect it. Otherwise mirror qty (current behaviour).
                orig_qty = _int_or_none(r.get("original_send_qty"))
                if orig_qty is None:
                    orig_qty = qty
                notes = r.get("notes")
                if notes is not None:
                    notes = str(notes).strip() or None

                cur.execute(
                    """
                    INSERT INTO plan_lines
                        (batch_id, sku, model, asin, destination_fc,
                         ship_from_wh, qty, original_send_qty, added_by,
                         real_am_inv, mother_inv, weekly_velocity, cb_soh,
                         hazmat, ixd_flag, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (batch_id, sku, destination_fc) DO NOTHING
                    """,
                    (
                        batch_id, sku,
                        str(r.get("model") or "").strip() or None,
                        str(r.get("asin")  or "").strip() or None,
                        fc,
                        str(r.get("ship_from_wh") or "").strip() or None,
                        qty, orig_qty, proposed_by,
                        _int_or_none(r.get("real_am_inv")),
                        _int_or_none(r.get("mother_inv")),
                        _float_or_none(r.get("weekly_velocity")),
                        _int_or_none(r.get("cb_soh")),
                        hazmat, ixd_flag,
                        notes,
                    ),
                )
            cur.execute(
                """
                INSERT INTO plan_line_events (batch_id, event_type, actor, payload_json)
                VALUES (%s, %s, %s, %s)
                """,
                (batch_id, "save_draft" if as_draft else "propose", proposed_by,
                 json.dumps({"row_count": len(rows), "account": account})),
            )
        conn.commit()
    return batch_id


def list_batches(account: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    where = []
    params: list[Any] = []
    if account:
        where.append("account = %s")
        params.append(account)
    if status:
        where.append("status = %s")
        params.append(status)
    sql = "SELECT * FROM plan_batches"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY proposed_at DESC LIMIT %s"
    params.append(limit)
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]


def get_batch(batch_id: str, include_deleted: bool = True) -> dict:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM plan_batches WHERE batch_id = %s", (batch_id,))
            b = cur.fetchone()
            if not b:
                raise ValueError(f"batch not found: {batch_id}")
            sql = "SELECT * FROM plan_lines WHERE batch_id = %s"
            if not include_deleted:
                sql += " AND is_deleted = FALSE"
            sql += " ORDER BY sku, destination_fc"
            cur.execute(sql, (batch_id,))
            lines = [dict(r) for r in cur.fetchall()]
            cur.execute(
                "SELECT * FROM plan_line_events WHERE batch_id = %s ORDER BY created_at DESC LIMIT 200",
                (batch_id,),
            )
            events = [dict(r) for r in cur.fetchall()]
    b = dict(b)
    # Backfill cb_soh for AA batches that were proposed before the
    # cb_soh column was wired (9303390 2026-08-12). Look up from live
    # CB Rep and fill in-memory only — don't mutate the snapshot, since
    # historical batches should reflect what Naresh saw at propose time.
    # New batches persist cb_soh at propose so this is a no-op for them.
    if str(b.get("account", "")).strip().lower() in ("audio array",) \
            and any(l.get("cb_soh") is None for l in lines):
        cb_map = _cached_cb_soh_map()
        if cb_map:
            for l in lines:
                if l.get("cb_soh") is None and l.get("model"):
                    key = str(l["model"]).split("(")[0].strip().lower()
                    if key in cb_map:
                        l["cb_soh"] = int(cb_map[key])
    b["lines"] = lines
    b["events"] = events
    b["summary"] = _summarize(lines)
    return b


def _summarize(lines: list[dict]) -> dict:
    active = [l for l in lines if not l.get("is_deleted")]
    total_units = sum(int(l.get("qty") or 0) for l in active)
    unique_skus = len({l["sku"] for l in active})
    unique_fcs  = len({l["destination_fc"] for l in active})
    added_by_approver = sum(1 for l in active if l.get("added_by") and l["added_by"] != active[0].get("added_by", ""))
    edited = sum(1 for l in active if l.get("edited_by"))
    deleted = sum(1 for l in lines if l.get("is_deleted"))
    original_total = sum(int(l.get("original_send_qty") or 0) for l in lines)
    return {
        "total_units": total_units,
        "unique_skus": unique_skus,
        "unique_fcs":  unique_fcs,
        "rows_active": len(active),
        "rows_deleted": deleted,
        "rows_edited":  edited,
        "rows_added_after_propose": added_by_approver,
        "original_total_units": original_total,
        "delta_units": total_units - original_total,
    }


# ============================================================
# LINE-LEVEL OPS (approver)
# ============================================================
def _assert_editable(cur, batch_id: str, actor: str, actor_is_admin: bool = False) -> dict:
    """Ensure the batch is in an editable state AND the actor is allowed
    to edit it.

    Draft:    proposer only.
    Proposed: proposer OR assigned approver (operator directive
              2026-08-13 — Naresh can patch minor things directly in
              Plans without recalling to Draft or re-proposing).
              row_version optimistic locking keeps concurrent edits safe.
    Approved / Pushed: nobody (create a new batch instead).

    Admin bypasses all checks. Returns the batch row (dict).
    """
    cur.execute(
        "SELECT batch_id, status, proposed_by, approver_email FROM plan_batches WHERE batch_id = %s",
        (batch_id,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"batch not found: {batch_id}")
    b = dict(row) if not isinstance(row, dict) else row
    status = b["status"]
    if status not in ("draft", "proposed"):
        raise ValueError(f"batch {batch_id} is {status}; not open for edits")
    if actor_is_admin:
        return b
    actor = (actor or "").strip().lower()
    proposer = (b.get("proposed_by") or "").strip().lower()
    if status == "draft":
        # Only the proposer can edit their own draft
        if proposer != actor:
            raise ValueError("only the draft's proposer (or an admin) can edit it")
    else:  # proposed
        target = (b.get("approver_email") or "").strip().lower()
        # Proposer can still edit their own proposed batch (small fixes
        # without recalling to draft). Assigned approver can edit too.
        if actor != proposer and target and actor != target:
            raise ValueError(
                f"this batch is addressed to {target} (or the proposer); "
                f"only they (or an admin) can edit"
            )
    return b


def edit_line(batch_id: str, line_id: int, new_qty: int | None, actor: str,
              row_version: int | None = None, actor_is_admin: bool = False,
              notes: str | None = None, approver_note: str | None = None,
              exclude_from_push: bool | None = None) -> dict:
    """Edit qty and/or notes and/or approver_note and/or exclude_from_push
    on a line. Pass None for a field to leave it unchanged. At least
    one must be provided.

    exclude_from_push: when True, the line stays in the batch (audit
    trail preserved) but push_plan() skips it. Used for stock at non-
    default warehouses (e.g. Turbhe) that need their own dispatch."""
    actor = (actor or "").strip().lower()
    if new_qty is None and notes is None and approver_note is None and exclude_from_push is None:
        raise ValueError("must provide qty, notes, approver_note, and/or exclude_from_push")
    if new_qty is not None:
        new_qty = int(round(float(new_qty)))
        if new_qty < 0:
            raise ValueError("qty must be >= 0")
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _assert_editable(cur, batch_id, actor, actor_is_admin)
            cur.execute(
                "SELECT * FROM plan_lines WHERE id = %s AND batch_id = %s",
                (line_id, batch_id),
            )
            line = cur.fetchone()
            if not line:
                raise ValueError(f"line {line_id} not found in {batch_id}")
            if row_version is not None and int(line["row_version"]) != int(row_version):
                raise ValueError(
                    f"stale row_version — line was edited by someone else "
                    f"(expected {row_version}, current {line['row_version']})"
                )
            old_qty = int(line["qty"])
            old_notes = line.get("notes")
            old_approver_note = line.get("approver_note")
            old_exclude = bool(line.get("exclude_from_push"))
            # Build a dynamic UPDATE that only touches the fields provided
            sets = ["edited_by = %s", "last_edited_at = NOW()", "row_version = row_version + 1"]
            vals: list = [actor]
            if new_qty is not None:
                sets.append("qty = %s")
                vals.append(new_qty)
            if notes is not None:
                sets.append("notes = %s")
                vals.append(notes)
            if approver_note is not None:
                sets.append("approver_note = %s")
                vals.append(approver_note or None)
            if exclude_from_push is not None:
                sets.append("exclude_from_push = %s")
                vals.append(bool(exclude_from_push))
            vals.append(line_id)
            cur.execute(
                f"UPDATE plan_lines SET {', '.join(sets)} WHERE id = %s RETURNING *",
                tuple(vals),
            )
            updated = dict(cur.fetchone())
            evt_payload: dict = {}
            if new_qty is not None and new_qty != old_qty:
                evt_payload["qty_from"] = old_qty
                evt_payload["qty_to"] = new_qty
            if notes is not None and notes != (old_notes or ""):
                evt_payload["notes_changed"] = True
            if approver_note is not None and approver_note != (old_approver_note or ""):
                evt_payload["approver_note"] = approver_note
            if exclude_from_push is not None and bool(exclude_from_push) != old_exclude:
                evt_payload["exclude_from_push"] = bool(exclude_from_push)
            if evt_payload:
                # Compose event_type from EVERY change so combined edits
                # (e.g., qty AND exclude_from_push in the same PATCH) show
                # both signals. Prior version was a mutually-exclusive
                # ladder that logged only "edit_qty" even when exclude
                # also changed — payload_json still carried the truth but
                # anyone filtering events by type would miss it.
                parts = []
                if "qty_to" in evt_payload:            parts.append("qty")
                if "notes_changed" in evt_payload:     parts.append("notes")
                if "approver_note" in evt_payload:     parts.append("approver_note")
                if "exclude_from_push" in evt_payload: parts.append("exclude")
                evt_type = "edit_" + "+".join(parts) if parts else "edit_line"
                cur.execute(
                    """
                    INSERT INTO plan_line_events (batch_id, line_id, event_type, actor, payload_json)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (batch_id, line_id, evt_type, actor, json.dumps(evt_payload)),
                )
        conn.commit()
    return updated


def add_line(
    batch_id: str,
    sku: str,
    destination_fc: str,
    qty: int,
    actor: str,
    model: str | None = None,
    asin: str | None = None,
    ship_from_wh: str | None = None,
    notes: str | None = None,
    actor_is_admin: bool = False,
) -> dict:
    sku = (sku or "").strip().upper()
    fc  = (destination_fc or "").strip().upper()
    actor = (actor or "").strip().lower()
    qty = int(round(float(qty)))
    if not sku or not fc:
        raise ValueError("sku and destination_fc are required")
    if qty <= 0:
        raise ValueError("qty must be > 0")
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _assert_editable(cur, batch_id, actor, actor_is_admin)
            # If a soft-deleted row exists for the same (batch, sku, fc), undelete
            # and update it instead of erroring out.
            cur.execute(
                "SELECT * FROM plan_lines WHERE batch_id = %s AND sku = %s AND destination_fc = %s",
                (batch_id, sku, fc),
            )
            existing = cur.fetchone()
            if existing:
                if not existing["is_deleted"]:
                    raise ValueError(f"line already exists for {sku} x {fc}; edit it instead")
                cur.execute(
                    """
                    UPDATE plan_lines
                    SET is_deleted = FALSE, deleted_by = NULL,
                        qty = %s, edited_by = %s, last_edited_at = NOW(),
                        row_version = row_version + 1,
                        model = COALESCE(%s, model),
                        asin  = COALESCE(%s, asin),
                        ship_from_wh = COALESCE(%s, ship_from_wh),
                        notes = COALESCE(%s, notes)
                    WHERE id = %s
                    RETURNING *
                    """,
                    (qty, actor, model, asin, ship_from_wh, notes, existing["id"]),
                )
                out = dict(cur.fetchone())
                cur.execute(
                    """
                    INSERT INTO plan_line_events (batch_id, line_id, event_type, actor, payload_json)
                    VALUES (%s, %s, 'undelete', %s, %s)
                    """,
                    (batch_id, out["id"], actor, json.dumps({"qty": qty})),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO plan_lines
                        (batch_id, sku, model, asin, destination_fc,
                         ship_from_wh, qty, original_send_qty, added_by, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s)
                    RETURNING *
                    """,
                    (batch_id, sku, model, asin, fc, ship_from_wh, qty, actor, notes),
                )
                out = dict(cur.fetchone())
                cur.execute(
                    """
                    INSERT INTO plan_line_events (batch_id, line_id, event_type, actor, payload_json)
                    VALUES (%s, %s, 'add', %s, %s)
                    """,
                    (batch_id, out["id"], actor,
                     json.dumps({"sku": sku, "destination_fc": fc, "qty": qty})),
                )
        conn.commit()
    return out


def delete_line(batch_id: str, line_id: int, actor: str, actor_is_admin: bool = False) -> dict:
    actor = (actor or "").strip().lower()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _assert_editable(cur, batch_id, actor, actor_is_admin)
            cur.execute(
                """
                UPDATE plan_lines
                SET is_deleted = TRUE, deleted_by = %s,
                    row_version = row_version + 1
                WHERE id = %s AND batch_id = %s AND is_deleted = FALSE
                RETURNING *
                """,
                (actor, line_id, batch_id),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"line {line_id} not found or already deleted")
            out = dict(row)
            cur.execute(
                """
                INSERT INTO plan_line_events (batch_id, line_id, event_type, actor, payload_json)
                VALUES (%s, %s, 'delete', %s, %s)
                """,
                (batch_id, line_id, actor, json.dumps({"qty": out["qty"]})),
            )
        conn.commit()
    return out


# ============================================================
# DELETE ENTIRE BATCH
# ============================================================
def delete_batch(batch_id: str, actor: str, actor_is_admin: bool = False) -> dict:
    """Hard-delete an entire batch and all its lines (FK cascade).

    Allowed:
      - status=draft     — only the proposer (or admin)
      - status=proposed  — the assigned approver (or admin)
      - status=approved  — admin only (approved plans stay for audit)
      - status=pushed    — admin only (avoid orphaning OrderPilot records)
    """
    actor = (actor or "").strip().lower()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT status, proposed_by, approver_email FROM plan_batches WHERE batch_id = %s",
                (batch_id,),
            )
            b = cur.fetchone()
            if not b:
                raise ValueError(f"batch not found: {batch_id}")
            status = b["status"]
            if not actor_is_admin:
                if status == "draft":
                    if (b.get("proposed_by") or "").strip().lower() != actor:
                        raise ValueError("only the draft's proposer (or admin) can delete it")
                elif status == "proposed":
                    target = (b.get("approver_email") or "").strip().lower()
                    if not target or actor != target:
                        raise ValueError(
                            f"this batch is addressed to {target}; only they (or admin) can delete"
                        )
                else:
                    raise ValueError(
                        f"batch is {status}; only admin can delete after approval to preserve audit trail"
                    )
            # Audit event BEFORE delete so it survives (plan_line_events has no FK to plan_batches)
            cur.execute(
                """
                INSERT INTO plan_line_events (batch_id, event_type, actor, payload_json)
                VALUES (%s, 'delete_batch', %s, %s)
                """,
                (batch_id, actor, json.dumps({"prior_status": status})),
            )
            cur.execute("DELETE FROM plan_batches WHERE batch_id = %s", (batch_id,))
        conn.commit()
    return {"batch_id": batch_id, "prior_status": status, "deleted_by": actor}


# ============================================================
# REQUEST REWORK (proposed -> draft, w/ feedback)
# ============================================================
def request_rework(batch_id: str, actor: str, feedback: str,
                   actor_is_admin: bool = False) -> dict:
    """Approver flips proposed -> draft with a feedback note. Editor
    (original proposer) can then edit + re-send. Only the assigned
    approver (or admin) can request rework."""
    actor = (actor or "").strip().lower()
    feedback = (feedback or "").strip()
    if not feedback:
        raise ValueError("feedback text is required for a rework request")
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT status, approver_email FROM plan_batches WHERE batch_id = %s",
                (batch_id,),
            )
            b = cur.fetchone()
            if not b:
                raise ValueError(f"batch not found: {batch_id}")
            if b["status"] != "proposed":
                raise ValueError(f"batch is {b['status']}; only 'proposed' can be sent for rework")
            if not actor_is_admin:
                target = (b.get("approver_email") or "").strip().lower()
                if target and actor != target:
                    raise ValueError(
                        f"this batch is addressed to {target}; only they (or admin) can request rework"
                    )
            cur.execute(
                """
                UPDATE plan_batches
                SET status = 'draft', approver_feedback = %s, updated_at = NOW()
                WHERE batch_id = %s
                RETURNING *
                """,
                (feedback, batch_id),
            )
            out = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO plan_line_events (batch_id, event_type, actor, payload_json)
                VALUES (%s, 'request_rework', %s, %s)
                """,
                (batch_id, actor, json.dumps({"feedback": feedback})),
            )
        conn.commit()
    return out


# ============================================================
# SEND (draft -> proposed)
# ============================================================
def send_to_approver(batch_id: str, actor: str, actor_is_admin: bool = False) -> dict:
    """Flip a draft batch to 'proposed' so the assigned approver can
    take over. Only the original proposer (or an admin) can send."""
    actor = (actor or "").strip().lower()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT status, proposed_by, approver_email FROM plan_batches WHERE batch_id = %s",
                (batch_id,),
            )
            b = cur.fetchone()
            if not b:
                raise ValueError(f"batch not found: {batch_id}")
            if b["status"] != "draft":
                raise ValueError(f"batch is {b['status']}; only 'draft' can be sent")
            if not actor_is_admin and (b.get("proposed_by") or "").strip().lower() != actor:
                raise ValueError("only the draft's proposer (or an admin) can send it")
            cur.execute(
                "SELECT COUNT(*) AS n FROM plan_lines WHERE batch_id = %s AND is_deleted = FALSE",
                (batch_id,),
            )
            n = int(cur.fetchone()["n"])
            if n == 0:
                raise ValueError("cannot send an empty draft (all lines deleted)")
            cur.execute(
                """
                UPDATE plan_batches
                SET status = 'proposed', updated_at = NOW()
                WHERE batch_id = %s
                RETURNING *
                """,
                (batch_id,),
            )
            out = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO plan_line_events (batch_id, event_type, actor, payload_json)
                VALUES (%s, 'send', %s, %s)
                """,
                (batch_id, actor, json.dumps({"active_lines": n, "approver": b.get("approver_email")})),
            )
        conn.commit()
    return out


# ============================================================
# APPROVAL + PUSH
# ============================================================
def approve_plan(batch_id: str, actor: str, actor_is_admin: bool = False) -> dict:
    actor = (actor or "").strip().lower()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT status, account, approver_email FROM plan_batches WHERE batch_id = %s",
                (batch_id,),
            )
            b = cur.fetchone()
            if not b:
                raise ValueError(f"batch not found: {batch_id}")
            if b["status"] != "proposed":
                raise ValueError(f"batch is {b['status']}; only 'proposed' can be approved")
            # Enforce approver targeting: if the batch was addressed to a
            # specific approver, only that person (or an admin) may approve.
            target = (b.get("approver_email") or "").strip().lower()
            if target and not actor_is_admin and actor != target:
                raise ValueError(
                    f"this batch is addressed to {target}; only they (or an admin) can approve"
                )
            # At least one non-deleted line must exist
            cur.execute(
                "SELECT COUNT(*) AS n FROM plan_lines WHERE batch_id = %s AND is_deleted = FALSE",
                (batch_id,),
            )
            n = int(cur.fetchone()["n"])
            if n == 0:
                raise ValueError("cannot approve an empty plan (all lines deleted)")
            cur.execute(
                """
                UPDATE plan_batches
                SET status = 'approved', approved_by = %s, approved_at = NOW(), updated_at = NOW()
                WHERE batch_id = %s
                RETURNING *
                """,
                (actor, batch_id),
            )
            out = dict(cur.fetchone())
            cur.execute(
                """
                INSERT INTO plan_line_events (batch_id, event_type, actor, payload_json)
                VALUES (%s, 'approve', %s, %s)
                """,
                (batch_id, actor, json.dumps({"active_lines": n})),
            )
        conn.commit()
    return out


def push_plan(batch_id: str, actor: str, dry_run: bool = False) -> dict:
    """Push an approved batch to OrderPilot's receiver.

    Reads env vars ORDERPILOT_PUSH_URL + ORDERPILOT_PUSH_TOKEN. Both must
    be set — else returns not_implemented (falls back to stub behavior).

    On 200:
      * status='pushed', pushed_at=NOW()
      * each line's orderpilot_shipment_id populated from response
        shipment_ids[destination_fc] map
      * push_success event logged with the response body
    On non-200:
      * status stays 'approved', push_error populated
      * push_failed event logged
      * caller can retry (OrderPilot is idempotent on batch_id)

    dry_run=True → appends ?dry_run=true; OrderPilot returns preview
    shipment_ids without persisting. Batch status does NOT flip on
    dry-run success — this is verify-wiring-only.
    """
    actor = (actor or "").strip().lower()
    url   = (os.environ.get("ORDERPILOT_PUSH_URL")   or "").strip()
    token = (os.environ.get("ORDERPILOT_PUSH_TOKEN") or "").strip()

    if not url or not token:
        # Fallback to stub if either env var is unset — makes the
        # cutover safe: forget one config value and we no-op instead of
        # POSTing garbage.
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO plan_line_events (batch_id, event_type, actor, payload_json)
                    VALUES (%s, 'push_stub_called', %s, %s)
                    """,
                    (batch_id, actor,
                     json.dumps({"note": "ORDERPILOT_PUSH_URL or _TOKEN unset"})),
                )
            conn.commit()
        return {"status": "not_implemented",
                "message": "ORDERPILOT_PUSH_URL/TOKEN not set",
                "batch_id": batch_id}

    # ---------------- Load batch + lines ----------------
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM plan_batches WHERE batch_id = %s", (batch_id,))
            b = cur.fetchone()
            if not b:
                raise ValueError(f"batch not found: {batch_id}")
            if b["status"] != "approved":
                raise ValueError(f"batch is {b['status']}; only 'approved' can be pushed")
            cur.execute(
                """SELECT * FROM plan_lines
                   WHERE batch_id = %s AND is_deleted = FALSE
                   ORDER BY id""",
                (batch_id,),
            )
            lines = [dict(r) for r in cur.fetchall()]

    if not lines:
        raise ValueError("no active lines to push")

    # ---------------- Build payload ----------------
    def _iso(dt):
        return dt.isoformat() if dt else None

    # OrderPilot's receiver enforces qty > 0. We deliberately store
    # zero-qty lines with a note (approver reads why=0) but those are
    # internal audit only — filter them out of the outbound payload.
    # exclude_from_push lines (approver toggle) also skipped: stock at
    # non-default warehouses like Turbhe that need their own dispatch.
    push_lines = [l for l in lines if int(l["qty"]) > 0 and not l.get("exclude_from_push")]
    skipped_zero = sum(1 for l in lines if int(l["qty"]) <= 0)
    skipped_excluded = sum(1 for l in lines if int(l["qty"]) > 0 and l.get("exclude_from_push"))
    if not push_lines:
        raise ValueError("no push-eligible lines (all rows zero-qty or excluded from push)")

    payload = {
        "source":         "am_replenishment",
        "batch_id":       b["batch_id"],
        "account":        b["account"],
        "source_module":  b.get("source_module"),
        "proposed_by":    b["proposed_by"],
        "approved_by":    b.get("approved_by"),
        "approved_at":    _iso(b.get("approved_at")),
        "lines": [
            {
                "line_id":         l["id"],
                "sku":             l["sku"],
                "model":           l.get("model"),
                "asin":            l.get("asin"),
                "destination_fc":  l["destination_fc"],
                "ship_from_wh":    l.get("ship_from_wh"),
                "qty":             int(l["qty"]),
                "notes":           l.get("notes"),
                # Split keys — OrderPilot MUST bucket by (destination_fc,
                # hazmat, ixd_flag) since Amazon FBA rejects mixed shipments.
                # Both null on Fossil / VENDOR path (1P Vendor Central).
                "hazmat":          l.get("hazmat"),
                "ixd_flag":        l.get("ixd_flag"),
            }
            for l in push_lines
        ],
    }
    if skipped_zero:
        print(f"[push_plan] batch {batch_id}: skipped {skipped_zero} zero-qty lines (kept in DB for audit)")
    if skipped_excluded:
        print(f"[push_plan] batch {batch_id}: skipped {skipped_excluded} exclude_from_push lines (kept in DB for audit)")

    # ---------------- POST ----------------
    target_url = url + ("?dry_run=true" if dry_run else "")
    try:
        resp = requests.post(
            target_url,
            json=payload,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type":  "application/json"},
            timeout=30,
        )
    except requests.RequestException as e:
        err_msg = f"network error: {type(e).__name__}: {e}"
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE plan_batches SET push_error = %s, updated_at = NOW() WHERE batch_id = %s",
                    (err_msg, batch_id),
                )
                cur.execute(
                    """INSERT INTO plan_line_events (batch_id, event_type, actor, payload_json)
                       VALUES (%s, 'push_failed', %s, %s)""",
                    (batch_id, actor, json.dumps({"error": err_msg, "dry_run": dry_run})),
                )
            conn.commit()
        return {"status": "error", "batch_id": batch_id, "error": err_msg}

    # ---------------- Handle response ----------------
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text[:500]}

    if resp.status_code == 200 and body.get("status") == "ok":
        shipment_ids = body.get("shipment_ids") or {}
        if dry_run:
            # Verify-only run — DO NOT persist status or line ids
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO plan_line_events (batch_id, event_type, actor, payload_json)
                           VALUES (%s, 'push_dry_run', %s, %s)""",
                        (batch_id, actor,
                         json.dumps({"shipment_ids": shipment_ids, "response": body})),
                    )
                conn.commit()
            return {"status": "ok", "dry_run": True, "batch_id": batch_id,
                    "preview_shipment_ids": shipment_ids}

        # Real push — flip status and store shipment IDs per line.
        # OrderPilot returns bucketed keys like "DEL4|H|IXD" (fc|H/N|IXD/N-IXD).
        # Fall back to bare fc key for Fossil VENDOR path or older receivers.
        def _bucket_key(l):
            fc = l["destination_fc"]
            hz = l.get("hazmat")
            ix = l.get("ixd_flag")
            if hz is None and ix is None:
                return fc  # Fossil VENDOR — never bucketed
            hz_c = "H" if hz else "N"
            ix_c = "N-IXD" if (ix or "").upper() == "NON IXD" else "IXD"
            return f"{fc}|{hz_c}|{ix_c}"

        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE plan_batches
                       SET status = 'pushed', pushed_at = NOW(), push_error = NULL, updated_at = NOW()
                       WHERE batch_id = %s""",
                    (batch_id,),
                )
                # Only iterate the lines we actually pushed. Zero-qty
                # audit lines stay in DB but don't get a shipment_id.
                for l in push_lines:
                    # Try bucketed key first, then bare fc for backward compat
                    sid = shipment_ids.get(_bucket_key(l)) or shipment_ids.get(l["destination_fc"])
                    if sid:
                        cur.execute(
                            """UPDATE plan_lines
                               SET orderpilot_shipment_id = %s, pushed_at = NOW()
                               WHERE id = %s""",
                            (sid, l["id"]),
                        )
                cur.execute(
                    """INSERT INTO plan_line_events (batch_id, event_type, actor, payload_json)
                       VALUES (%s, 'push_success', %s, %s)""",
                    (batch_id, actor,
                     json.dumps({"shipment_ids": shipment_ids, "response": body})),
                )
            conn.commit()
        return {"status": "ok", "batch_id": batch_id, "shipment_ids": shipment_ids}

    # Non-200 or status != ok
    err_msg = f"HTTP {resp.status_code}: {body.get('detail') or body.get('raw') or json.dumps(body)[:200]}"
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE plan_batches SET push_error = %s, updated_at = NOW() WHERE batch_id = %s",
                (err_msg, batch_id),
            )
            cur.execute(
                """INSERT INTO plan_line_events (batch_id, event_type, actor, payload_json)
                   VALUES (%s, 'push_failed', %s, %s)""",
                (batch_id, actor,
                 json.dumps({"status_code": resp.status_code, "response": body, "dry_run": dry_run})),
            )
        conn.commit()
    return {"status": "error", "batch_id": batch_id, "error": err_msg, "response": body}
