from fastapi import APIRouter, Query
from app.services.replenishment import calculate_replenishment
from app.services.fc_final_allocation import calculate_final_allocation

# =================================================
# ROUTER SETUP
# =================================================
router = APIRouter(
    prefix="",
    tags=["replenishment"],
)

# =================================================
# REPLENISHMENT ENDPOINT
# =================================================
@router.get("/replenishment")
def get_replenishment(
    sales_window: int = Query(default=4, ge=1),
    replenish_weeks: int = Query(default=8, ge=1),
):
    df = calculate_replenishment(sales_window, replenish_weeks)

    response = []

    for _, row in df.iterrows():
        response.append({
            "model": row["Model"],
            "sales_velocity": int(row["sales_velocity"]),
            "total_units_sold": int(row["total_units_sold"]),
            "amazon_inventory": int(row["amazon_inventory"]),
            "ampm_inventory": int(row["ampm_inventory"]),
            "required_units": int(row["required_units"]),
            "replenishment_qty": int(row["replenishment_qty"]),
            "warehouse_shortfall": int(row["warehouse_shortfall"]),
            "is_risky": bool(row["is_risky"]),
            "is_overstock": bool(row["is_overstock"]),
        })

    return response


# =================================================
# FC FINAL ALLOCATION ENDPOINT
# =================================================
@router.get("/fc-final")
def get_fc_final(
    replenish_weeks: int = Query(default=8, ge=1),
):
    df = calculate_final_allocation(replenish_weeks)

    response = []

    for _, row in df.iterrows():
        response.append({
            "sku": row["sku"],
            "fulfillment_center": row["fulfillment_center"],
            "weekly_velocity": int(row["weekly_velocity"]),
            "fc_inventory": int(row["fc_inventory"]),
            "transfer_in": int(row["transfer_in"]),
            "target_cover_units": int(row["target_cover_units"]),
            "post_transfer_stock": int(row["post_transfer_stock"]),
            "coverage_gap_units": int(row["coverage_gap_units"]),
            "send_qty": int(row["send_qty"]),
        })

    return response