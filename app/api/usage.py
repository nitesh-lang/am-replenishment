from fastapi import APIRouter, Request
from app.services import usage_log
from app.services.auth_tokens import require_admin


router = APIRouter(tags=["usage"])


@router.post("/usage/log")
async def post_event(request: Request):
    """Fire-and-forget logging. Caller passes user_email in body OR X-User-Email header."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    email = body.get("user_email") or request.headers.get("x-user-email") or None

    # Coerce module carefully — str(None) would store "None" as a string
    raw_module = body.get("module")
    module = raw_module.strip() if isinstance(raw_module, str) and raw_module.strip() else None

    usage_log.log_event(
        user_email=email,
        event_type=str(body.get("event_type", "")).strip(),
        module=module,
        detail=body.get("detail") or {},
    )
    return {"status": "ok"}


@router.get("/usage/summary")
def get_summary(request: Request):
    """Admin-only aggregated analytics."""
    require_admin(request)
    return {"status": "ok", **usage_log.summary()}
