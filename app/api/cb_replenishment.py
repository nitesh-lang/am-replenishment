from fastapi import APIRouter
from app.services.cb_replenishment import load_cb_replenishment

router = APIRouter(
    prefix="/cb-replenishment",
    tags=["CB Replenishment"]
)


@router.get("/")
def get_cb_replenishment():

    try:

        # =========================
        # LOAD DATA FROM SERVICE
        # =========================

        df = load_cb_replenishment()

        print("CB REPLENISHMENT ROWS:", len(df))

        # =========================
        # HANDLE EMPTY DATA
        # =========================

        if df is None or df.empty:
            return {
                "data": [],
                "total_models": 0,
                "message": "No data returned from service"
            }

        # =========================
        # FORMAT RESPONSE
        # =========================

        response_df = df[[
            "brand",
            "model",
            "final_cb_qty",
            "cb_3m_sales",
            "cambium_3m_sales",
            "avg_weekly_sales",
            "estimated_qty",
            "deficiency",
            "open_po",
            "in_transit",
            "po_requirement"
        ]]

        return {
            "data": response_df.to_dict(orient="records"),
            "total_models": len(response_df)
        }

    except Exception as e:

        print("CB API ERROR:", str(e))

        return {
            "data": [],
            "total_models": 0,
            "error": str(e)
        }