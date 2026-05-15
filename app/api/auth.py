from fastapi import APIRouter, Request, HTTPException
from app.services import auth_users


router = APIRouter(tags=["auth"])


# =========================================================
# Public — login & current user
# =========================================================
@router.post("/auth/login")
async def login(request: Request):
    body = await request.json()
    email = str(body.get("email", "")).strip()
    password = str(body.get("password", ""))
    if not email or not password:
        return {"status": "error", "error": "email and password are required"}
    user = auth_users.authenticate(email, password)
    if not user:
        return {"status": "error", "error": "Invalid email or password"}
    return {"status": "ok", "user": user}


@router.get("/auth/me")
def me(email: str):
    user = auth_users.get_user(email)
    if not user:
        return {"status": "error", "error": "Not found"}
    return {"status": "ok", "user": user}


# =========================================================
# Admin — user management
# Auth via X-Admin-Email header. Header must belong to a
# user with role=admin. Mirrors the existing simple model.
# =========================================================
def _require_admin(request: Request):
    email = request.headers.get("x-admin-email", "").strip()
    if not email or not auth_users.is_admin(email):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/admin/users")
def list_users(request: Request):
    _require_admin(request)
    return {"status": "ok", "users": auth_users.list_users(), "modules": auth_users.ALL_MODULES}


@router.post("/admin/users")
async def create_or_update(request: Request):
    _require_admin(request)
    body = await request.json()
    try:
        user = auth_users.upsert_user(
            email=str(body.get("email", "")),
            name=str(body.get("name", "")),
            password=body.get("password") or None,
            role=str(body.get("role", "user")),
            allowed_modules=body.get("allowed_modules", []) or [],
        )
        return {"status": "ok", "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/admin/users/{email}")
def remove(email: str, request: Request):
    _require_admin(request)
    try:
        ok = auth_users.delete_user(email)
        if not ok:
            raise HTTPException(status_code=404, detail="User not found")
        return {"status": "ok"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
