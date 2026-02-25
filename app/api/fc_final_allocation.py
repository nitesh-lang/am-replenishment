from fastapi import APIRouter, Query
from app.services.fc_final_allocation import calculate_final_allocation

# =================================================
# ROUTER SETUP
# =================================================
router = APIRouter(
    prefix="",
    tags=["fc-final-allocation"],
)

# =================================================
# FINAL FC ALLOCATION ENDPOINT
# =================================================
@router.get("/fc-final-allocation")
def get_fc_final_allocation(
    replenish_weeks: int = Query(
        default=8,
        ge=1,
        description="Number of weeks to plan FC-level replenishment for",
    ),
    channel: str = Query(
        default="All",
        description="Sales Channel filter: All / Amazon.in / Non-Amazon"
    ),
    account: str = Query(   # ✅ ADDED
        default="Nexlev",
        description="Account selector: Nexlev / Viomi"
    )
):
    """
    Final FC Allocation API
    """

    df = calculate_final_allocation(
        replenish_weeks=replenish_weeks,
        channel=channel,
        account=account
    )

    if df is None or df.empty:
        return []

    return df.to_dict(orient="records")