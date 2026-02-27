from fastapi import APIRouter, Query
from typing import Optional
from app.services.china_reorder_working import get_china_reorder_working_data

router = APIRouter(
    prefix="/api",
    tags=["china-reorder-working"],
)


@router.get("/china-reorder-working")
def china_reorder_working(
    brand: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
):
    return get_china_reorder_working_data(
        brand=brand,
        channel=channel,
        model=model,
    )