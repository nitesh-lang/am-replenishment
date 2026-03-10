from fastapi import APIRouter
from app.services.fossil_replenishment_service import load_fossil_replenishment

router = APIRouter()

@router.get("/fossil-replenishment")
def get_fossil_replenishment(weeks: int = 8):

    df = load_fossil_replenishment(weeks)

    return {
        "data": df.to_dict(orient="records"),
        "total_skus": len(df)
    }