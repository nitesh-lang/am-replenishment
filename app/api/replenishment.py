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
    account: str = Query(default="NEXLEV"),
):
    df = calculate_replenishment(sales_window, replenish_weeks, account)

    response = []

    for _, row in df.iterrows():
        response.append({
            "model": row["model"],
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
@router.get("/fc-final-allocation")
def get_fc_final(
    replenish_weeks: int = Query(default=8, ge=1),
):
    df = calculate_final_allocation(replenish_weeks)

    return df.to_dict(orient="records")