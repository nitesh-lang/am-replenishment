from fastapi import APIRouter, Query
from app.services.data_freshness import check_module, MODULES

router = APIRouter(prefix="", tags=["data-freshness"])


@router.get("/data-freshness")
def get_data_freshness(module: str = Query(..., description="module key, e.g. cb-replenishment")):
    if module not in MODULES:
        return {"error": f"unknown module: {module}", "known_modules": list(MODULES.keys())}
    return check_module(module)
