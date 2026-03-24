from fastapi import APIRouter
from app.services.fossil_replenishment_service import load_fossil_replenishment

router = APIRouter(prefix="/api")

@router.get("/fossil-replenishment")
def get_fossil_replenishment():

    df = load_fossil_replenishment()

    return {
        "data": df.to_dict(orient="records"),
        "total_skus": len(df)
    }