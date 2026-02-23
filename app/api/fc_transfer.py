from fastapi import APIRouter, Query
from app.services.fc_transfer import calculate_fc_transfers

router = APIRouter(
    prefix="",
    tags=["fc-transfer"],
)

@router.get("/fc-transfer")
def get_fc_transfers(
    replenish_weeks: int = Query(default=8, ge=1)
):

    df = calculate_fc_transfers(replenish_weeks)

    return df.to_dict(orient="records")