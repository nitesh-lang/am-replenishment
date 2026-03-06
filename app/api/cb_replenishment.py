from fastapi import APIRouter
from app.services.cb_replenishment import load_cb_replenishment

router = APIRouter(
    prefix="/cb-replenishment",
    tags=["CB Replenishment"]
)

@router.get("/")
def get_cb_replenishment():

    df = load_cb_replenishment()

    # debug print
    print("ROWS RETURNED:", len(df))

    if df.empty:
        return {
            "data": [],
            "total_models": 0,
            "message": "No data returned from service"
        }

    return {
        "data": df.to_dict(orient="records"),
        "total_models": len(df)
    }