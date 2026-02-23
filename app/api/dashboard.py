from fastapi import APIRouter, Query
from app.services.replenishment import calculate_replenishment

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# =========================
# RISKY MODELS (DISABLED)
# =========================
# Already captured via replenishment service,
# not required separately in UI

# @router.get("/risky-models")
# def risky_models(weeks: int = Query(4)):
#     df = calculate_replenishment(weeks)
#
#     # SAFETY: if dataframe is empty
#     if df.empty:
#         return []
#
#     # Risky = needs replenishment
#     risky = df[df["replenishment_qty"] > 0]
#
#     return risky[
#         [
#             "Model",
#             "sales_velocity",
#             "Total AM Inventory",
#             "AMPM",
#             "required_units",
#             "replenishment_qty",
#         ]
#     ].to_dict(orient="records")


# =========================
# OVERSTOCK (DISABLED)
# =========================
# Already derived in replenishment logic,
# no separate API exposure needed

# @router.get("/overstock")
# def overstock(weeks: int = Query(4)):
#     df = calculate_replenishment(weeks)
#
#     # SAFETY: if dataframe is empty
#     if df.empty:
#         return []
#
#     # Overstock = inventory more than 8 weeks of sales
#     over = df[df["Total AM Inventory"] > (df["sales_velocity"] * 8)]
#
#     return over[
#         [
#             "Model",
#             "sales_velocity",
#             "Total AM Inventory",
#             "AMPM",
#         ]
#     ].to_dict(orient="records")