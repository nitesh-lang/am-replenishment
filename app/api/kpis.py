from fastapi import APIRouter
from sqlalchemy import text
from app.db import get_engine

router = APIRouter(prefix="/kpis", tags=["kpis"])
engine = get_engine()

@router.get("/")
def get_kpis():
    q = """
    SELECT
        COALESCE(SUM(reorder_qty), 0) AS total_units_to_replenish,
        COUNT(*) FILTER (WHERE weeks_of_cover < 2) AS risky_models_count,
        COUNT(*) FILTER (WHERE weeks_of_cover > 10) AS overstock_models_count,
        AVG(weeks_of_cover) AS avg_weeks_of_cover
    FROM replenishment_plan
    """
    with engine.connect() as c:
        row = c.execute(text(q)).mappings().first()
        return row or {
            "total_units_to_replenish": 0,
            "risky_models_count": 0,
            "overstock_models_count": 0,
            "avg_weeks_of_cover": None
        }