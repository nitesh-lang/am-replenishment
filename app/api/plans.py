"""
Plan approval workflow endpoints.

  POST   /plans/propose                         -> plans-editor
  GET    /plans                                 -> plans-editor OR plans-approver (list)
  GET    /plans/{batch_id}                      -> plans-editor OR plans-approver
  PATCH  /plans/{batch_id}/lines/{line_id}      -> plans-approver (edit qty)
  POST   /plans/{batch_id}/lines                -> plans-approver (add row)
  DELETE /plans/{batch_id}/lines/{line_id}      -> plans-approver (soft delete)
  POST   /plans/{batch_id}/approve              -> plans-approver
  POST   /plans/{batch_id}/push                 -> plans-approver (STUB: not wired)

Auth: Authorization: Bearer <token>. Admins bypass module checks.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from app.services import plans_service, auth_users
from app.services.auth_tokens import require_module


def _ok(payload: dict, status_code: int = 200) -> JSONResponse:
    """JSONResponse wrapper that handles datetime + other non-JSON-native
    types via FastAPI's jsonable_encoder. Every list/get/mutate endpoint
    that returns DB rows must route through this — plan_batches has
    timestamp columns (proposed_at/approved_at/created_at/updated_at)
    that the raw json module can't serialize."""
    return JSONResponse(jsonable_encoder(payload), status_code=status_code)


router = APIRouter(tags=["plans"])


def _editor(request: Request) -> str:
    return require_module(request, "plans-editor")


def _approver(request: Request) -> str:
    return require_module(request, "plans-approver")


def _either(request: Request) -> str:
    """Editor OR approver (or admin, via require_module's admin bypass)."""
    try:
        return require_module(request, "plans-editor")
    except HTTPException:
        return require_module(request, "plans-approver")


def _editor_or_approver(request: Request) -> str:
    """Same as _either but named for line-edit endpoints where either role
    can perform the action depending on batch status (service enforces)."""
    return _either(request)


# ============================================================
# LIST / GET
# ============================================================
@router.get("/plans")
def list_plans(request: Request, account: str | None = None, status: str | None = None, limit: int = 50):
    _either(request)
    rows = plans_service.list_batches(account=account, status=status, limit=limit)
    return _ok({"status": "ok", "batches": rows})


@router.get("/plans/{batch_id}")
def get_plan(batch_id: str, request: Request, include_deleted: bool = True):
    _either(request)
    try:
        return _ok({"status": "ok", "batch": plans_service.get_batch(batch_id, include_deleted=include_deleted)})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================
# PROPOSE (editor)
# ============================================================
@router.post("/plans/propose")
async def propose(request: Request):
    """Snapshot rows into a batch. Body may include `as_draft=true` to
    park in the draft state (editor-editable, not yet sent to approver)."""
    actor = _editor(request)
    body = await request.json()
    account         = body.get("account")
    week_tag        = body.get("week_tag")
    rows            = body.get("rows") or []
    source_module   = body.get("source_module")
    approver_email  = body.get("approver_email")
    as_draft        = bool(body.get("as_draft"))
    try:
        batch_id = plans_service.propose_plan(
            account=account, proposed_by=actor, week_tag=week_tag, rows=rows,
            source_module=source_module, approver_email=approver_email,
            as_draft=as_draft,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"status": "ok", "batch_id": batch_id})


@router.post("/plans/save-draft")
async def save_draft(request: Request):
    """Convenience wrapper — always creates in status='draft'."""
    actor = _editor(request)
    body = await request.json()
    try:
        batch_id = plans_service.propose_plan(
            account=body.get("account"),
            proposed_by=actor,
            week_tag=body.get("week_tag"),
            rows=body.get("rows") or [],
            source_module=body.get("source_module"),
            approver_email=body.get("approver_email"),
            as_draft=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"status": "ok", "batch_id": batch_id})


@router.post("/plans/{batch_id}/send")
def send(batch_id: str, request: Request):
    """Editor sends their draft to the assigned approver."""
    actor = _editor(request)
    is_admin = auth_users.is_admin(actor)
    try:
        out = plans_service.send_to_approver(batch_id, actor, actor_is_admin=is_admin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"status": "ok", "batch": out})


# ============================================================
# LINE EDITS (approver)
# ============================================================
@router.patch("/plans/{batch_id}/lines/{line_id}")
async def patch_line(batch_id: str, line_id: int, request: Request):
    actor = _editor_or_approver(request)
    is_admin = auth_users.is_admin(actor)
    body = await request.json()
    if "qty" not in body:
        raise HTTPException(status_code=400, detail="qty is required")
    try:
        out = plans_service.edit_line(
            batch_id=batch_id, line_id=line_id,
            new_qty=int(body["qty"]), actor=actor,
            row_version=body.get("row_version"),
            actor_is_admin=is_admin,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"status": "ok", "line": out})


@router.post("/plans/{batch_id}/lines")
async def post_line(batch_id: str, request: Request):
    actor = _editor_or_approver(request)
    is_admin = auth_users.is_admin(actor)
    body = await request.json()
    try:
        out = plans_service.add_line(
            batch_id=batch_id,
            sku=body.get("sku", ""),
            destination_fc=body.get("destination_fc", ""),
            qty=int(body.get("qty", 0)),
            actor=actor,
            model=body.get("model"),
            asin=body.get("asin"),
            ship_from_wh=body.get("ship_from_wh"),
            notes=body.get("notes"),
            actor_is_admin=is_admin,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"status": "ok", "line": out}, status_code=201)


@router.delete("/plans/{batch_id}/lines/{line_id}")
def del_line(batch_id: str, line_id: int, request: Request):
    actor = _editor_or_approver(request)
    is_admin = auth_users.is_admin(actor)
    try:
        out = plans_service.delete_line(batch_id=batch_id, line_id=line_id,
                                        actor=actor, actor_is_admin=is_admin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"status": "ok", "line": out})


# ============================================================
# APPROVE + PUSH
# ============================================================
@router.post("/plans/{batch_id}/approve")
def approve(batch_id: str, request: Request):
    actor = _approver(request)
    is_admin = auth_users.is_admin(actor)
    try:
        out = plans_service.approve_plan(batch_id=batch_id, actor=actor, actor_is_admin=is_admin)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _ok({"status": "ok", "batch": out})


@router.post("/plans/{batch_id}/push")
def push(batch_id: str, request: Request):
    actor = _approver(request)
    try:
        out = plans_service.push_plan(batch_id=batch_id, actor=actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # STUB returns 202 Accepted with the not-implemented status so callers
    # can distinguish "we accepted the call but haven't wired the bridge"
    # from a real success/failure.
    return _ok(out, status_code=202)
