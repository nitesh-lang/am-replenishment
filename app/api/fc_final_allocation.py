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

    response = []

    for _, row in df.iterrows():
        response.append(
            {
                # Identity
                "model": row.get("model"),   # ✅ ADD THIS
                "sku": row.get("sku"),
                "fulfillment_center": row.get("fulfillment_center"),

                # Core metrics
                "weekly_velocity": int(round(row.get("weekly_velocity", 0))),
                "fc_inventory": int(round(row.get("fc_inventory", 0))),
                "transfer_in": int(round(row.get("transfer_in", 0))),

                # Planning metrics
                "target_cover_units": int(round(row.get("target_cover_units", 0))),
                "post_transfer_stock": int(round(row.get("post_transfer_stock", 0))),
                "coverage_gap_units": int(round(row.get("coverage_gap_units", 0))),

               # Final output
               "send_qty": int(round(row.get("send_qty", 0))),
               "expected_units": int(round(row.get("expected_units", 0))),
               "velocity_fill_ratio": float(row.get("velocity_fill_ratio", 0)),
               "velocity_flag": row.get("velocity_flag"),
               "allocation_logic": row.get("allocation_logic"),
            }
        )

    return response