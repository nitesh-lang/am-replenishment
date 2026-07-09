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
from app.api.cb_replenishment import router as cb_replenishment_router
from app.api.wm_replenishment import router as wm_replenishment_router
from app.api.fossil_replenishment import router as fossil_router
from app.api.blinkit_replenishment import router as blinkit_router
from app.api.inbound_shipments import router as inbound_shipments_router
from app.api.data_freshness import router as data_freshness_router
from app.api.master_carton import router as master_carton_router
from app.api.auth import router as auth_router
from app.api.usage import router as usage_router



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
    try:
        from app.services import auth_users
        auth_users.ensure_table_and_seed()
        print("✅ App users table ready")
    except Exception as e:
        print(f"⚠️ User table init warning: {e}")
    try:
        from app.services import usage_log
        usage_log.ensure_table()
        print("✅ Usage log table ready")
    except Exception as e:
        print(f"⚠️ Usage log init warning: {e}")
    _preload_data_files()

def _preload_data_files():
    """Pre-load all heavy Excel/CSV files into memory at startup."""
    try:
        from app.services import file_cache
        file_cache.preload()
        print("✅ Data files preloaded into cache")
    except Exception as e:
        print(f"⚠️ Preload warning: {e}")
# =====================================================
# CORS (REQUIRED FOR VITE FRONTEND)
# =====================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://am-replenishment-1.onrender.com",
        "https://am-replenishment.onrender.com",
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
# Alias the same router under /api so stale frontend bundles that call
# /api/replenishment?... don't 404 spam. Both prefixes hit the same code.
app.include_router(replenishment_router, prefix="/api")
app.include_router(dashboard_router)
app.include_router(fc_planning_router)
app.include_router(fc_transfer_router)
app.include_router(fc_final_allocation_router)
app.include_router(region_sales_router)  # ✅ NEW
app.include_router(china_reorder_router)
app.include_router(cb_replenishment_router, prefix="/api")
app.include_router(wm_replenishment_router, prefix="/api")
app.include_router(fossil_router)
app.include_router(blinkit_router, prefix="/api")
app.include_router(inbound_shipments_router)
app.include_router(data_freshness_router)
app.include_router(master_carton_router)
app.include_router(auth_router)
app.include_router(usage_router)

# =====================================================
# ROOT
# =====================================================
@app.get("/")
def root():
    return {
        "message": "AM Inventory Replenishment API running"
    }