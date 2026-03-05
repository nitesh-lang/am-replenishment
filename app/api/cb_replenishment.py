from fastapi import APIRouter
from app.services.cb_replenishment import load_cb_replenishment

router = APIRouter(
    prefix="/cb-replenishment",
    tags=["CB Replenishment"]
)

@router.get("/")
def get_cb_replenishment():

    try:
        df = load_cb_replenishment()

        return {
            "data": df.to_dict(orient="records"),
            "total_models": len(df)
        }

    except Exception as e:
        return {
            "error": str(e)
        }