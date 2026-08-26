"""Replenishment Watchlist API.

GET  /watchlist              -> signal rows + counts
GET  /watchlist/email-draft  -> editable email draft for the accounts in scope

Read-only. Nothing here writes or sends — the email is a DRAFT the operator
copies out and sends themselves. No SMTP is wired deliberately: sending mail
to the CEO on a background job's say-so is not something this tool should be
able to do without a human pressing send.
"""
from fastapi import APIRouter, Query

from app.services import replen_watchlist

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


def _accounts(account: str | None) -> list[str] | None:
    if not account:
        return None
    return [a.strip() for a in account.split(",") if a.strip()]


@router.get("")
def get_watchlist(
    account: str | None = Query(
        default=None,
        description="Comma-separated accounts; omit for all four. Fossil is "
                    "always excluded (no ASIN Type, separate PO flow).",
    ),
    sales_window: int = Query(default=12, ge=1, le=52),
    replenish_weeks: int = Query(default=8, ge=1, le=52),
    velocity_mode: str = Query(default="max"),
):
    return replen_watchlist.build_watchlist(
        accounts=_accounts(account),
        sales_window=sales_window,
        replenish_weeks=replenish_weeks,
        velocity_mode=velocity_mode,
    )


@router.get("/email-draft")
def get_email_draft(
    account: str | None = Query(default=None),
    sales_window: int = Query(default=12, ge=1, le=52),
    replenish_weeks: int = Query(default=8, ge=1, le=52),
    velocity_mode: str = Query(default="max"),
    week_tag: str | None = Query(default=None),
):
    wl = replen_watchlist.build_watchlist(
        accounts=_accounts(account),
        sales_window=sales_window,
        replenish_weeks=replenish_weeks,
        velocity_mode=velocity_mode,
    )
    # Default the week to the same "latest completed sales week" the Plans
    # module stamps, so the email and the plan batches agree on the period.
    wk = week_tag
    if not wk:
        try:
            from app.services.plans_service import latest_sales_week
            wk = latest_sales_week()
        except Exception:
            wk = None
    draft = replen_watchlist.build_email_draft(wl, week_tag=wk)
    draft["counts"] = wl.get("counts", {})
    return draft
