from fastapi import APIRouter, Query
from typing import Optional
import pandas as pd
import os
from app.services.china_reorder import china_reorder_logic

router = APIRouter(prefix="/china-reorder", tags=["China Reorder"])


@router.get("/")
def get_china_reorder(
    brand: str = Query(..., description="Brand name"),
    months: int = Query(3, ge=1, le=6, description="Planning horizon in months"),
    channel: str = Query("All", description="Sales channel filter"),
    from_week: Optional[int] = Query(default=None),
    to_week:   Optional[int] = Query(default=None),
):
    data = china_reorder_logic(brand, months, channel, from_week, to_week)

    try:
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sales_path = os.path.join(BASE_DIR, "..", "data", "input", "weekly_sales_snapshot - ChinaReorder.csv")
        raw = pd.read_csv(sales_path)
        raw.columns = raw.columns.str.strip().str.lower()
        raw["brand"] = raw["brand"].astype(str).str.strip().str.lower()
        raw = raw[raw["brand"] == brand.strip().lower()]
        raw["week_num"] = raw["week"].astype(str).str.extract(r"(\d+)")[0].pipe(pd.to_numeric, errors="coerce")
        available_weeks = sorted(raw["week_num"].dropna().unique().tolist(), reverse=True)[:12]
        available_weeks = sorted([int(w) for w in available_weeks])
    except:
        available_weeks = []

    return {"data": data, "available_weeks": available_weeks}