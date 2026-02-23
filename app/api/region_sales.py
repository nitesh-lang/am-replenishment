from fastapi import APIRouter, HTTPException, Query
from app.services.region_sales import calculate_region_sales

router = APIRouter(prefix="/region-sales", tags=["Region Sales"])

@router.get("/")
def get_region_sales(
    account: str = Query(default="Nexlev")
):
    """
    Returns region-wise sales (last 30 days)
    Includes:
    - total_units_30d
    - weekly_velocity
    - revenue_30d
    """

    try:
        df = calculate_region_sales(account=account)

        if df.empty:
            return []

        # Convert to JSON-friendly format
        return df.to_dict(orient="records")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))