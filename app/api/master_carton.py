from fastapi import APIRouter
from sqlalchemy import text
from app.db import engine

# =====================================================
# ROUTER SETUP
# =====================================================
router = APIRouter(
    prefix="",
    tags=["master-carton"]
)


# =====================================================
# SAVE MASTER CARTON
# =====================================================
@router.post("/save-master-carton")
def save_master_carton(data: dict):
    model = data.get("model")
    master_carton = data.get("master_carton")

    if not model:
        return {"status": "error", "message": "model missing"}

    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO master_cartons (model, master_carton)
                VALUES (:model, :master_carton)
                ON CONFLICT (model)
                DO UPDATE SET master_carton = :master_carton
            """),
            {
                "model": model,
                "master_carton": master_carton
            }
        )
        conn.commit()

    return {
        "status": "saved",
        "model": model,
        "master_carton": master_carton
    }


# =====================================================
# GET MASTER CARTONS (LOAD ON UI REFRESH)
# =====================================================
@router.get("/get-master-cartons")
def get_master_cartons():

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT model, master_carton FROM master_cartons")
        ).fetchall()

    response = []

    for row in result:
        response.append({
            "model": row[0],
            "master_carton": row[1]
        })

    return response