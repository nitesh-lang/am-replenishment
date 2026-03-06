from fastapi import APIRouter
from app.services.cb_replenishment import load_cb_replenishment

router = APIRouter(
    prefix="/cb-replenishment",
    tags=["CB Replenishment"]
)


@router.get("/")
def get_cb_replenishment():
    try:

        # Load dataframe from service
        df = load_cb_replenishment()

        # Debug log
        print("CB REPLENISHMENT ROWS:", len(df))

        # If no data
        if df is None or df.empty:
            return {
                "data": [],
                "total_models": 0,
                "message": "No data returned from service"
            }

        # Return response
        return {
            "data": df.to_dict(orient="records"),
            "total_models": len(df)
        }

    except Exception as e:

        print("CB API ERROR:", str(e))

        return {
            "data": [],
            "total_models": 0,
            "error": str(e)
        }