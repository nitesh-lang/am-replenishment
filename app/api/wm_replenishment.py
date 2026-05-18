from fastapi import APIRouter, Request, Query
from typing import Optional
from app.services.wm_replenishment import load_wm_replenishment
from app.services.db import get_conn
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
def get_wm_replenishment(
    from_week: Optional[int] = Query(default=None, ge=1, le=52),
    to_week:   Optional[int] = Query(default=None, ge=1, le=52),
    cover_weeks: int = Query(default=8, ge=1, le=52),
):

    try:
        df = load_wm_replenishment(
            from_week=from_week,
            to_week=to_week,
            cover_weeks=cover_weeks,
        )

        print(f"WM REPLENISHMENT ROWS: {len(df)} | window: {from_week}→{to_week} | cover: {cover_weeks}w")

        if df is None or df.empty:
            return {
                "data": [],
                "total_models": 0,
                "message": "No data returned from service"
            }

        # =========================
        # FETCH SAVED DATA FROM DB
        # =========================
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT model, po_requirement, remarks FROM wm_inputs")
                saved_data = cursor.fetchall()

        saved_df = pd.DataFrame(
            saved_data,
            columns=["model", "po_requirement_db", "remarks_db"]
        )

        if not saved_df.empty:
            df = df.merge(saved_df, on="model", how="left")

            # Restore saved po_requirement and remarks — fresh calc only if no DB value
            if "po_requirement_db" in df.columns:
                df["po_requirement"] = df["po_requirement_db"].combine_first(df["po_requirement"])
                df = df.drop(columns=["po_requirement_db"], errors="ignore")
            if "remarks_db" in df.columns:
                df["remarks"] = df["remarks_db"].fillna("")
                df = df.drop(columns=["remarks_db"], errors="ignore")

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

        try:
            raw_sales = pd.read_csv("data/input/weekly_sales_snapshot.csv")
            raw_sales.columns = raw_sales.columns.str.lower().str.strip()
            raw_sales = raw_sales[raw_sales["brand"] == "White Mulberry"]
            print("WM RAW SALES ROWS:", len(raw_sales))
            raw_sales["week_num"] = raw_sales["week"].astype(str).str.extract(r"(\d+)")[0].pipe(pd.to_numeric, errors="coerce")
            print("WM AVAILABLE WEEKS:", sorted(raw_sales["week_num"].dropna().unique().tolist()))
            available_weeks = sorted(
                raw_sales["week_num"].dropna().unique().tolist(),
                reverse=True
            )[:12]
            available_weeks = sorted([int(w) for w in available_weeks])
        except:
            available_weeks = []

        return {
            "data": response_df.to_dict(orient="records"),
            "total_models": len(response_df),
            "available_weeks": available_weeks
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

        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS wm_inputs (
                        model TEXT PRIMARY KEY,
                        po_requirement INTEGER DEFAULT 0,
                        remarks TEXT DEFAULT ''
                    )
                """)
                cursor.execute("ALTER TABLE wm_inputs ADD COLUMN IF NOT EXISTS po_requirement INTEGER DEFAULT 0")
                cursor.execute("ALTER TABLE wm_inputs ADD COLUMN IF NOT EXISTS remarks TEXT DEFAULT ''")
                conn.commit()

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

        return {"status": "saved"}

    except Exception as e:
        print("WM SAVE ERROR:", str(e))
        return {"status": "error", "error": str(e)}

# =========================
# RESET API
# =========================
@router.post("/reset")
async def reset_wm_inputs():
    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM wm_inputs")
            conn.commit()
        return {"status": "reset"}
    except Exception as e:
        print("WM RESET ERROR:", str(e))
        return {"status": "error", "error": str(e)}
