from fastapi import APIRouter, Request, Query
from app.services.cb_replenishment import load_cb_replenishment
import psycopg2
import os
import json
import pandas as pd

router = APIRouter(
    prefix="/cb-replenishment",
    tags=["CB Replenishment"]
)

# =========================
# GET API (LOAD DATA)
# =========================
@router.get("/")
def get_cb_replenishment(
    from_week: int = Query(default=52, ge=1, le=52),
    to_week:   int = Query(default=11, ge=1, le=52),
    cover_weeks: int = Query(default=8, ge=1, le=52),
):

    try:
        df = load_cb_replenishment(
            from_week=from_week,
            to_week=to_week,
            cover_weeks=cover_weeks,
        )

        print(f"CB REPLENISHMENT ROWS: {len(df)} | window: {from_week}→{to_week} | cover: {cover_weeks}w")

        if df is None or df.empty:
            return {
                "data": [],
                "total_models": 0,
                "message": "No data returned from service"
            }

        # ✅ FETCH SAVED DATA FROM DB
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cursor = conn.cursor()

        cursor.execute("SELECT model, po_requirement, remarks FROM cb_inputs")
        saved_data = cursor.fetchall()

        conn.close()

        # ✅ CONVERT TO DF
        saved_df = pd.DataFrame(
            saved_data,
            columns=["model", "po_requirement_db", "remarks_db"]
        )

        # ✅ SAFE MERGE
        if not saved_df.empty:
            df = df.merge(saved_df, on="model", how="left")

            if "po_requirement_db" in df.columns:
                df["po_requirement"] = df["po_requirement_db"].fillna(df["po_requirement"])

            if "remarks_db" in df.columns:
                df["remarks"] = df["remarks_db"].fillna(df.get("remarks", ""))

        # =========================
        # FINAL RESPONSE
        # =========================
        response_df = df[[
            "brand",
            "model",
            "china_in_transit",
            "final_cb_qty",
            "ampm_inventory",
            "cb_3m_sales",
            "cambium_3m_sales",
            "avg_weekly_sales",
            "estimated_qty",
            "deficiency",
            "open_po",
            "in_transit",
            "po_requirement",
            "remarks",
            "hazmat_type"
        ]].copy()

        for col in ["avg_weekly_sales", "estimated_qty", "deficiency", "cb_3m_sales", "cambium_3m_sales"]:
            if col in response_df.columns:
                response_df[col] = response_df[col].round(0).astype(int)

        return {
            "data": response_df.to_dict(orient="records"),
            "total_models": len(response_df)
        }

    except Exception as e:
        print("CB API ERROR:", str(e))
        return {
            "data": [],
            "total_models": 0,
            "error": str(e)
        }


# =========================
# SAVE API
# =========================
@router.post("/save")
async def save_cb_inputs(request: Request):

    try:
        data = await request.json()

        # handle string / dict / list
        if isinstance(data, str):
            data = json.loads(data)

        if isinstance(data, dict):
            data = [data]

        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cursor = conn.cursor()

        for row in data:
            model = row.get("model")
            po_requirement = int(row.get("po_requirement", 0))
            remarks = row.get("remarks", "")

            cursor.execute("""
                INSERT INTO cb_inputs (model, po_requirement, remarks)
                VALUES (%s, %s, %s)
                ON CONFLICT (model)
                DO UPDATE SET
                    po_requirement = EXCLUDED.po_requirement,
                    remarks = EXCLUDED.remarks;
            """, (model, po_requirement, remarks))

        conn.commit()
        conn.close()

        return {"status": "saved"}

    except Exception as e:
        print("CB SAVE ERROR:", str(e))
        return {"status": "error", "error": str(e)}
