from fastapi import APIRouter, Request
from app.services.wm_replenishment import load_wm_replenishment
import psycopg2
import os
import json
import pandas as pd

router = APIRouter(
    prefix="/wm-replenishment",
    tags=["WM Replenishment"]
)

# =========================
# GET API (LOAD DATA)
# =========================
@router.get("/")
def get_wm_replenishment():

    try:
        df = load_wm_replenishment()

        print("WM REPLENISHMENT ROWS:", len(df))

        if df is None or df.empty:
            return {
                "data": [],
                "total_models": 0,
                "message": "No data returned from service"
            }

        # =========================
        # FETCH SAVED DATA FROM DB
        # =========================
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cursor = conn.cursor()

        cursor.execute("SELECT model, po_requirement, remarks FROM wm_inputs")
        saved_data = cursor.fetchall()

        conn.close()

        saved_df = pd.DataFrame(
            saved_data,
            columns=["model", "po_requirement_db", "remarks_db"]
        )

        if not saved_df.empty:
            df = df.merge(saved_df, on="model", how="left")

            if "po_requirement_db" in df.columns:
                df["po_requirement"] = df["po_requirement_db"].fillna(df["po_requirement"])

            if "remarks_db" in df.columns:
                df["remarks"] = df["remarks_db"].fillna("")

            df = df.drop(columns=["po_requirement_db", "remarks_db"], errors="ignore")

        # =========================
        # FINAL RESPONSE
        # =========================
        for col in ["hazmat_type", "category"]:
            if col not in df.columns:
                df[col] = "-"

        response_df = df[[
            "model",
            "category",
            "hazmat_type",
            "final_cb_qty",
            "ampm_inventory",
            "cb_3m_sales",
            "amazon_3m_sales",
            "avg_weekly_sales",
            "estimated_qty",
            "deficiency",
            "open_po",
            "in_transit",
            "po_requirement",
            "remarks"
        ]]

        return {
            "data": response_df.to_dict(orient="records"),
            "total_models": len(response_df)
        }

    except Exception as e:
        print("WM API ERROR:", str(e))
        return {
            "data": [],
            "total_models": 0,
            "error": str(e)
        }


# =========================
# SAVE API
# =========================
@router.post("/save")
async def save_wm_inputs(request: Request):

    try:
        data = await request.json()

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
                INSERT INTO wm_inputs (model, po_requirement, remarks)
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
        print("WM SAVE ERROR:", str(e))
        return {"status": "error", "error": str(e)}