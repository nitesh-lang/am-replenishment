from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
import io

from app.services.fc_final_allocation import calculate_final_allocation


# =================================================
# ROUTER SETUP
# =================================================
router = APIRouter(
    prefix="",
    tags=["fc-final-allocation"],
)


# =================================================
# FINAL FC ALLOCATION DATA API
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
    account: str = Query(
        default="Nexlev",
        description="Account selector: Nexlev / Viomi"
    )
):
    """
    Final FC Allocation API (JSON)
    """

    print("🚨 ACCOUNT FROM API:", account)

    df = calculate_final_allocation(
        replenish_weeks=replenish_weeks,
        channel=channel,
        account=account
    )

    if df is None or df.empty:
        return []

    return df.to_dict(orient="records")


# =================================================
# FINAL FC ALLOCATION EXPORT API (CSV)
# =================================================
@router.get("/fc-final-allocation/export")
def export_fc_final_allocation(
    replenish_weeks: int = 8,
    channel: str = "All",
    account: str = "Nexlev"
):
    """
    Final FC Allocation Export API (CSV)
    """

    print("🚨 EXPORT ACCOUNT FROM API:", account)

    df = calculate_final_allocation(
        replenish_weeks=replenish_weeks,
        channel=channel,
        account=account
    )

    if df is None or df.empty:
        return []

    stream = io.StringIO()
    df.to_csv(stream, index=False)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=fc_allocation.csv"
        }
    )