import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import HTTPException, Request

from app.services import auth_users


# =========================================================
# Secret key
#
# Source from AUTH_SECRET_KEY env var. If unset we fall back
# to a per-process random key — that keeps the API secure
# (forgeries impossible) but invalidates every session on
# restart. Set AUTH_SECRET_KEY in the deploy environment to
# get stable sessions across restarts/workers.
# =========================================================
_DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24h

_SECRET = os.environ.get("AUTH_SECRET_KEY", "").strip()
if not _SECRET:
    _SECRET = secrets.token_hex(32)
    print(
        "⚠️  AUTH_SECRET_KEY not set — generated an ephemeral key. "
        "All sessions will invalidate on restart. "
        "Set AUTH_SECRET_KEY in the environment for stable sessions."
    )
_SECRET_BYTES = _SECRET.encode()


# =========================================================
# Token format: <payload_b64url>.<hmac_sha256_hex>
#   payload = {"email": "...", "role": "...", "exp": <unix>}
# =========================================================
def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _sign(payload_b64: str) -> str:
    return hmac.new(_SECRET_BYTES, payload_b64.encode(), hashlib.sha256).hexdigest()


def make_token(email: str, role: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> str:
    payload = {
        "email": (email or "").strip().lower(),
        "role":  role,
        "exp":   int(time.time()) + int(ttl_seconds),
    }
    payload_b64 = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    return f"{payload_b64}.{_sign(payload_b64)}"


def verify_token(token: str) -> dict | None:
    """Return the payload dict if the token is valid and unexpired, else None."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig = token.rsplit(".", 1)
    except ValueError:
        return None

    if not hmac.compare_digest(_sign(payload_b64), sig):
        return None

    try:
        payload = json.loads(_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None

    exp = payload.get("exp")
    if not isinstance(exp, int) or exp < int(time.time()):
        return None

    return payload


# =========================================================
# FastAPI dependency — reads Authorization: Bearer <token>,
# verifies the signature, then re-checks role from the DB
# so demotion/deletion takes effect immediately.
# =========================================================
def _bearer(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return ""
    return auth[7:].strip()


def require_admin(request: Request) -> str:
    """Return the authenticated admin's email or raise 401/403."""
    payload = verify_token(_bearer(request))
    if not payload:
        raise HTTPException(status_code=401, detail="Authentication required")
    email = payload.get("email", "")
    if not email or not auth_users.is_admin(email):
        raise HTTPException(status_code=403, detail="Admin access required")
    return email


def require_module(request: Request, module: str) -> str:
    """Return the authenticated user's email if they have the given
    module in allowed_modules OR they are an admin. Raise 401/403.
    """
    payload = verify_token(_bearer(request))
    if not payload:
        raise HTTPException(status_code=401, detail="Authentication required")
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="Authentication required")
    if auth_users.is_admin(email):
        return email
    user = auth_users.get_user(email)
    if not user:
        raise HTTPException(status_code=403, detail="Unknown user")
    allowed = user.get("allowed_modules") or []
    if module not in allowed:
        raise HTTPException(status_code=403, detail=f"Access to '{module}' required")
    return email
