from fastapi import APIRouter, Query
from app.services.replenishment import calculate_replenishment

router = APIRouter()


@router.get("/replenishment")
def replenishment(weeks: int = Query(4)):
    df = calculate_replenishment(weeks)

    return df[
        [
            "Model",
            "sales_velocity",
            "Total AM Inventory",
            "AMPM",
            "required_units",
            "replenishment_qty",
        ]
    ].to_dict(orient="records")

@router.get("/kpis")
def kpis(weeks: int = Query(4)):
    df = calculate_replenishment(weeks)

    return {
        "total_models": int(df["Model"].nunique()),
        "models_to_replenish": int((df["replenishment_qty"] > 0).sum()),
        "total_units_to_ship": int(
            df.loc[df["replenishment_qty"] > 0, "replenishment_qty"].sum()
        ),
    }