from fastapi import APIRouter
from sqlalchemy import text
from app.db import engine

router = APIRouter()

@router.post("/save-master-carton")
def save_master_carton(data: dict):
    model = data["model"]
    carton = data["master_carton"]

    with engine.connect() as conn:
        conn.execute(
            text("""
            INSERT INTO master_cartons (model, master_carton)
            VALUES (:model, :carton)
            ON CONFLICT (model)
            DO UPDATE SET master_carton = :carton
            """),
            {"model": model, "carton": carton}
        )
        conn.commit()

    return {"status": "saved"}