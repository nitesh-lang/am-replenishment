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


def _csv(value: str | None) -> list[str] | None:
    if not value:
        return None
    out = [a.strip() for a in value.split(",") if a.strip()]
    return out or None


def _accounts(account: str | None) -> list[str] | None:
    return _csv(account)


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
    asin_type: str | None = Query(
        default=None,
        description="Comma-separated ASIN Types to keep; omit for all.",
    ),
    lost_basis: str = Query(
        default="avg",
        description="Benchmark for lost-units: avg (default) | 2wk | peak. "
                    "Watchlist-only — other tabs keep the historical peak basis.",
    ),
):
    return replen_watchlist.build_watchlist(
        accounts=_accounts(account),
        sales_window=sales_window,
        replenish_weeks=replenish_weeks,
        velocity_mode=velocity_mode,
        asin_types=_csv(asin_type),
        lost_basis=lost_basis,
    )


@router.get("/email-draft")
def get_email_draft(
    account: str | None = Query(default=None),
    sales_window: int = Query(default=12, ge=1, le=52),
    replenish_weeks: int = Query(default=8, ge=1, le=52),
    velocity_mode: str = Query(default="max"),
    week_tag: str | None = Query(default=None),
    asin_type: str | None = Query(default=None),
    lost_basis: str = Query(default="avg"),
):
    # Same filter args as GET /watchlist, so the draft always describes exactly
    # the set the operator has on screen.
    wl = replen_watchlist.build_watchlist(
        accounts=_accounts(account),
        sales_window=sales_window,
        replenish_weeks=replenish_weeks,
        velocity_mode=velocity_mode,
        asin_types=_csv(asin_type),
        lost_basis=lost_basis,
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
