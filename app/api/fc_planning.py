from fastapi import APIRouter, Query
from typing import Optional
from app.services.fc_planning import calculate_fc_plan

router = APIRouter(
    prefix="/fc-planning",
    tags=["fc-planning"],
)

# =================================================
# MAIN FC PLANNING ENDPOINT
# =================================================
@router.get("")
def get_fc_planning(
    replenish_weeks: int = Query(default=8, ge=1),
    sku: Optional[str] = None,
    fc: Optional[str] = None,
):
    df = calculate_fc_plan(replenish_weeks)

    # -----------------------------
    # OPTIONAL FILTERS
    # -----------------------------
    if sku:
        df = df[df["Merchant SKU"] == sku]

    if fc:
        df = df[df["FC"] == fc]

    # -----------------------------
    # RETURN JSON (FAST)
    # -----------------------------
    return df.to_dict(orient="records")


# =================================================
# SUMMARY ENDPOINT
# =================================================
@router.get("/summary")
def get_fc_summary(
    replenish_weeks: int = Query(default=8, ge=1),
):
    df = calculate_fc_plan(replenish_weeks)

    summary = (
        df.groupby("Merchant SKU", as_index=False)
        .agg(
            total_required=("required_units", "sum"),
            total_inventory=("fc_inventory", "sum"),
            total_shortfall=("fc_shortfall", "sum"),
        )
    )

    return summary.to_dict(orient="records")