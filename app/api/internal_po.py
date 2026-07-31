"""Internal PO endpoints — powers the "PO Creation" tab.

Contracts:
  GET  /selling-accounts        -> [{id, name}] read from stored SP-API creds
  POST /internal-po             -> create + forward to OrderPilot ingest
  POST /internal-po/draft       -> save draft (no OrderPilot forward)
  GET  /internal-po/recent      -> local history (last 50)
  GET  /internal-po/drafts      -> saved drafts
"""
from typing import Any

from fastapi import APIRouter, Request

from app.services.internal_po import (
    create_internal_po,
    list_recent,
    list_selling_accounts,
)


router = APIRouter(tags=["Internal PO"])


@router.get("/selling-accounts")
def get_selling_accounts() -> dict[str, Any]:
    return {"data": list_selling_accounts()}


@router.post("/internal-po")
async def post_internal_po(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        result = create_internal_po(
            selling_account=body.get("selling_account") or {},
            brand=str(body.get("brand", "")).strip(),
            week_range=str(body.get("week_range", "")).strip(),
            cover=int(body.get("cover", 0) or 0),
            created_by=str(body.get("created_by", "")).strip(),
            lines=body.get("lines") or [],
            is_draft=False,
        )
        return {"status": "ok", "pos": result}
    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        print("⚠️ /internal-po failed:", e)
        return {"status": "error", "error": str(e)}


@router.post("/internal-po/draft")
async def post_internal_po_draft(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
        result = create_internal_po(
            selling_account=body.get("selling_account") or {},
            brand=str(body.get("brand", "")).strip(),
            week_range=str(body.get("week_range", "")).strip(),
            cover=int(body.get("cover", 0) or 0),
            created_by=str(body.get("created_by", "")).strip(),
            lines=body.get("lines") or [],
            is_draft=True,
        )
        return {"status": "ok", "pos": result}
    except ValueError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        print("⚠️ /internal-po/draft failed:", e)
        return {"status": "error", "error": str(e)}


@router.get("/internal-po/recent")
def get_recent() -> dict[str, Any]:
    try:
        return {"data": list_recent(limit=50, drafts_only=False)}
    except Exception as e:
        return {"data": [], "error": str(e)}


@router.get("/internal-po/drafts")
def get_drafts() -> dict[str, Any]:
    try:
        return {"data": list_recent(limit=50, drafts_only=True)}
    except Exception as e:
        return {"data": [], "error": str(e)}
