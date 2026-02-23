from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# =====================================================
# IMPORT ROUTERS
# =====================================================
from app.api.kpis import router as kpis_router
from app.api.replenishment import router as replenishment_router
from app.api.dashboard import router as dashboard_router
from app.api.fc_planning import router as fc_planning_router
from app.api.fc_transfer import router as fc_transfer_router
from app.api.fc_final_allocation import router as fc_final_allocation_router
from app.api.region_sales import router as region_sales_router  # ✅ NEW


# =====================================================
# CREATE APP
# =====================================================
app = FastAPI(
    title="AM Inventory Replenishment API",
    version="1.0.0"
)

# =====================================================
# CORS (REQUIRED FOR VITE FRONTEND)
# =====================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # 🔥 change this
    allow_methods=["*"],
    allow_headers=["*"],
)

# =====================================================
# HEALTH CHECK
# =====================================================
@app.get("/health")
def health():
    return {"status": "ok"}


# =====================================================
# INCLUDE ROUTERS
# =====================================================
app.include_router(kpis_router)
app.include_router(replenishment_router)
app.include_router(dashboard_router)
app.include_router(fc_planning_router)
app.include_router(fc_transfer_router)
app.include_router(fc_final_allocation_router)
app.include_router(region_sales_router)  # ✅ NEW


# =====================================================
# ROOT
# =====================================================
@app.get("/")
def root():
    return {
        "message": "AM Inventory Replenishment API running"
    }