from fastapi import APIRouter, HTTPException, Query
from app.services.region_sales import calculate_region_sales

# =================================================
# ROUTER SETUP
# =================================================
router = APIRouter(
    prefix="/region-sales",
    tags=["Region Sales"]
)

# =================================================
# REGION SALES ENDPOINT
# =================================================
@router.get("/")
def get_region_sales(
    account: str = Query(default="NEXLEV")
):
    """
    Returns region-wise sales (last 30 days)
    Includes:
    - total_units_30d
    - weekly_velocity
    - revenue_30d
    """

    try:
        df = calculate_region_sales(account=account.upper())

        if df.empty:
            return []

        return df.to_dict(orient="records")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))