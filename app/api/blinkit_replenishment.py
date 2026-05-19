from fastapi import APIRouter, Query

from app.services.blinkit_replenishment import load_blinkit_replenishment


router = APIRouter(
    prefix="/blinkit-replenishment",
    tags=["Blinkit Replenishment"],
)


# Cover-weeks options exposed to the frontend dropdown
COVER_WEEKS_OPTIONS = [2, 4, 6, 8, 10, 12]


@router.get("/")
def get_blinkit_replenishment(
    cover_weeks: int = Query(default=8, ge=1, le=52),
):
    try:
        df = load_blinkit_replenishment(cover_weeks=cover_weeks)

        if df is None or df.empty:
            return {
                "data": [],
                "total_skus": 0,
                "cover_weeks_options": COVER_WEEKS_OPTIONS,
                "message": "No data returned from service",
            }

        # Final column order for the frontend
        cols = [
            "brand", "model", "sku", "asin", "item_id", "expansion_level",
            "category_l1", "category_l2",
            "master_carton",
            "blinkit_soh", "ampm_inv",
            "total_sales_3m", "avg_weekly_sales",
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
            "cover_weeks_options": COVER_WEEKS_OPTIONS,
        }

    except Exception as e:
        print("BLINKIT API ERROR:", str(e))
        return {
            "data": [],
            "total_skus": 0,
            "cover_weeks_options": COVER_WEEKS_OPTIONS,
            "error": str(e),
        }
