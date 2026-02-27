from dotenv import load_dotenv
load_dotenv()
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
from app.api.china_reorder import router as china_reorder_router


# =====================================================
# CREATE APP
# =====================================================
app = FastAPI(
    title="AM Inventory Replenishment API",
    version="1.0.0"
)
from app.db import engine
from app.core.models.base import Base

@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)
# =====================================================
# CORS (REQUIRED FOR VITE FRONTEND)
# =====================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://am-replenishment-1.onrender.com",
    ],
    allow_credentials=True,
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
app.include_router(china_reorder_router)

# =====================================================
# ROOT
# =====================================================
@app.get("/")
def root():
    return {
        "message": "AM Inventory Replenishment API running"
    }