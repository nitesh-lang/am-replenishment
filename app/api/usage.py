from fastapi import APIRouter, Request, HTTPException
from app.services import usage_log, auth_users


router = APIRouter(tags=["usage"])


@router.post("/usage/log")
async def post_event(request: Request):
    """Fire-and-forget logging. Caller passes user_email in body OR X-User-Email header."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    email = body.get("user_email") or request.headers.get("x-user-email") or None
    usage_log.log_event(
        user_email=email,
        event_type=str(body.get("event_type", "")).strip(),
        module=str(body.get("module", "")).strip() or None,
        detail=body.get("detail") or {},
    )
    return {"status": "ok"}


@router.get("/usage/summary")
def get_summary(request: Request):
    """Admin-only aggregated analytics."""
    email = request.headers.get("x-admin-email", "").strip()
    if not email or not auth_users.is_admin(email):
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"status": "ok", **usage_log.summary()}
