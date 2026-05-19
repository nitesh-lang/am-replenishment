from typing import Optional

from fastapi import APIRouter, Query

from app.services.blinkit_replenishment import (
    get_available_blinkit_weeks,
    get_available_monthly_weeks,
    load_blinkit_replenishment,
    load_blinkit_statewise,
)


router = APIRouter(
    prefix="/blinkit-replenishment",
    tags=["Blinkit Replenishment"],
)


# Cover-weeks options exposed to the frontend dropdown
COVER_WEEKS_OPTIONS = [2, 4, 6, 8, 10, 12]


@router.get("/")
def get_blinkit_replenishment(
    cover_weeks: int = Query(default=8, ge=1, le=52),
    from_week:   Optional[int] = Query(default=None, ge=1, le=53),
    to_week:     Optional[int] = Query(default=None, ge=1, le=53),
):
    try:
        df, window = load_blinkit_replenishment(
            cover_weeks=cover_weeks,
            from_week=from_week,
            to_week=to_week,
        )

        available_weeks = get_available_blinkit_weeks()

        meta = {
            "cover_weeks_options": COVER_WEEKS_OPTIONS,
            "available_weeks":     available_weeks,
            "selected_window":     {
                "from_week": from_week,
                "to_week":   to_week,
                "weeks_in_window": window,
            },
        }

        if df is None or df.empty:
            return {
                "data": [],
                "total_skus": 0,
                **meta,
                "message": "No data returned from service",
            }

        # Final column order for the frontend.
        # Note: 'asin' is kept in the payload so it shows up in the CSV export
        # even though the UI table hides it.
        cols = [
            "brand", "model", "sku", "item_id", "product_id", "asin", "expansion_level",
            "category_l1", "category_l2",
            "master_carton",
            "blinkit_soh", "ampm_inv",
            "total_sales_window", "avg_weekly_sales",
            "required_units", "deficiency", "warehouse_shortfall", "send_qty",
        ]
        cols = [c for c in cols if c in df.columns]
        response_df = df[cols].copy()

        # JSON-safe: replace NaN/inf, coerce item_id to plain int
        response_df = response_df.fillna("")
        if "item_id" in response_df.columns:
            response_df["item_id"] = response_df["item_id"].apply(
                lambda v: int(v) if v != "" else ""
            )

        return {
            "data": response_df.to_dict(orient="records"),
            "total_skus": len(response_df),
            **meta,
        }

    except Exception as e:
        print("BLINKIT API ERROR:", str(e))
        return {
            "data": [],
            "total_skus": 0,
            "cover_weeks_options": COVER_WEEKS_OPTIONS,
            "available_weeks": [],
            "error": str(e),
        }


@router.get("/statewise")
def get_blinkit_replenishment_statewise(
    cover_weeks: int = Query(default=8, ge=1, le=52),
    from_week:   Optional[int] = Query(default=None, ge=1, le=53),
    to_week:     Optional[int] = Query(default=None, ge=1, le=53),
):
    """Per-SKU × per-Customer-State view. Sales come from the monthly
    Blinkit order exports (the only source with state info). Weeks are
    ISO-week numbers derived from each order's date."""
    try:
        df, window = load_blinkit_statewise(
            cover_weeks=cover_weeks,
            from_week=from_week,
            to_week=to_week,
        )

        available_weeks = get_available_monthly_weeks()

        meta = {
            "cover_weeks_options": COVER_WEEKS_OPTIONS,
            "available_weeks":     available_weeks,
            "selected_window":     {
                "from_week": from_week,
                "to_week":   to_week,
                "weeks_in_window": window,
            },
        }

        if df is None or df.empty:
            return {
                "data": [],
                "total_rows": 0,
                **meta,
                "message": "No order data in the selected window",
            }

        cols = [
            "brand", "model", "sku", "item_id", "product_id",
            "customer_state",
            "state_sales", "state_share_pct", "state_avg_weekly",
            "state_required",
            "state_soh", "blinkit_soh", "state_deficiency",
            "ampm_inv",
            "total_sales_window",
            "asin", "expansion_level", "category_l1",
        ]
        cols = [c for c in cols if c in df.columns]
        response_df = df[cols].copy().fillna("")
        if "item_id" in response_df.columns:
            response_df["item_id"] = response_df["item_id"].apply(
                lambda v: int(v) if v != "" else ""
            )

        return {
            "data": response_df.to_dict(orient="records"),
            "total_rows": len(response_df),
            **meta,
        }

    except Exception as e:
        print("BLINKIT STATEWISE API ERROR:", str(e))
        return {
            "data": [],
            "total_rows": 0,
            "cover_weeks_options": COVER_WEEKS_OPTIONS,
            "available_weeks": [],
            "error": str(e),
        }
