print("RUNNING CORE MAIN")
from fastapi import FastAPI
from app.api import replenishment
from app.api import dashboard
from app.api import kpis
from app.api import fc_planning   # 👈 ADD THIS
from app.api import region_sales

app = FastAPI()

app.include_router(replenishment.router)
app.include_router(dashboard.router)
app.include_router(kpis.router)
app.include_router(fc_planning.router)   # 👈 ADD THIS
app.include_router(region_sales.router)