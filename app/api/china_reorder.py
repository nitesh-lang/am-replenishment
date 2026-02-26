from fastapi import APIRouter, Query
from app.services.china_reorder import china_reorder_logic

router = APIRouter(prefix="/china-reorder", tags=["China Reorder"])

@router.get("/")
def get_china_reorder(brand: str = Query(...)):
    return china_reorder_logic(brand)