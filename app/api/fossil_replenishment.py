from fastapi import APIRouter, Query
from typing import Optional
from app.services.fossil_replenishment_service import load_fossil_replenishment

router = APIRouter(prefix="/api")

@router.get("/fossil-replenishment")
def get_fossil_replenishment(
    from_week: Optional[int] = Query(None),
    to_week: Optional[int] = Query(None),
    cover_weeks: Optional[int] = Query(None),
):

    df, available_weeks = load_fossil_replenishment(
        from_week=from_week,
        to_week=to_week,
        cover_weeks=cover_weeks,
    )

    return {
        "data": df.to_dict(orient="records"),
        "total_skus": len(df),
        "available_weeks": available_weeks,
    }