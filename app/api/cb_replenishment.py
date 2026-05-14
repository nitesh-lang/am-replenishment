from fastapi import APIRouter, Request, Query
from typing import Optional
from app.services.cb_replenishment import load_cb_replenishment
from app.services import cb_replenishment_saved
from app.services.week_helper import (
    current_working_week_start,
    week_end,
    week_label,
    is_week_locked,
    now_ist,
)
from datetime import date as _date
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
    from_week: Optional[int] = Query(default=None, ge=1, le=52),
    to_week:   Optional[int] = Query(default=None, ge=1, le=52),
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

        saved_df = pd.DataFrame(saved_data, columns=["model", "po_requirement_db", "remarks_db"])

        # Restore saved po_requirement and remarks — fresh calc only if no DB value
        if not saved_df.empty:
            df = df.merge(saved_df, on="model", how="left")
            if "po_requirement_db" in df.columns:
                df["po_requirement"] = df["po_requirement_db"].combine_first(df["po_requirement"])
                df = df.drop(columns=["po_requirement_db"], errors="ignore")
            if "remarks_db" in df.columns:
                df["remarks"] = df["remarks_db"].fillna("")
                df = df.drop(columns=["remarks_db"], errors="ignore")

        # ✅ MERGE WEEK-SCOPED WORKING VALUE + REMARKS (current working week)
        try:
            cb_replenishment_saved.ensure_table()
            week_map = cb_replenishment_saved.load_current_week_map(current_working_week_start())
            df["working_value"] = df["model"].map(
                lambda m: week_map.get(str(m), {}).get("working_value", "")
            )
            # Week-scoped remarks override the legacy remarks if present
            df["remarks_week"] = df["model"].map(
                lambda m: week_map.get(str(m), {}).get("remarks", "")
            )
            df["remarks"] = df.apply(
                lambda r: r["remarks_week"] if str(r.get("remarks_week", "")).strip() else r.get("remarks", ""),
                axis=1,
            )
            df = df.drop(columns=["remarks_week"], errors="ignore")
        except Exception as e:
            print("⚠️ Could not load week-scoped CB working values:", e)
            df["working_value"] = ""

        # =========================
        # FINAL RESPONSE
        # =========================
        response_df = df[[
            "brand",
            "model",
            "asin",
            "sku",
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
            "working_value",
            "remarks",
            "hazmat_type"
        ]].copy()

        # Master column "Hazmat Type" is actually ASIN Sort Details
        response_df = response_df.rename(columns={"hazmat_type": "asin_sort_details"})

        for col in ["avg_weekly_sales", "estimated_qty", "deficiency", "cb_3m_sales", "cambium_3m_sales"]:
            if col in response_df.columns:
                response_df[col] = response_df[col].round(0).astype(int)

        # Get last 12 available weeks for frontend dropdowns
        try:
            raw_sales = pd.read_csv("data/input/weekly_sales_snapshot - CB Replenishment.csv")
            raw_sales["week_num"] = raw_sales["week"].astype(str).str.extract(r"(\d+)")[0].pipe(pd.to_numeric, errors="coerce")
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
        print("CB API ERROR:", str(e))
        return {
            "data": [],
            "total_models": 0,
            "error": str(e)
        }


# =========================
# WEEK-SCOPED SAVE — auto-save per row (working_value + remarks)
# =========================
@router.post("/save-working")
async def cb_save_working_row(request: Request):
    try:
        body = await request.json()
        model = str(body.get("model", "")).strip()
        if not model:
            return {"status": "error", "error": "model required"}

        ws = current_working_week_start()
        if is_week_locked(ws):
            return {
                "status": "locked",
                "error":  f"Working week ({week_label(ws)}) is past Saturday 11:59 PM IST.",
                "week_start": ws.isoformat(),
            }

        cb_replenishment_saved.ensure_table()
        cb_replenishment_saved.save_row(
            week_start=ws,
            model=model,
            working_value=body.get("working_value"),
            remarks=body.get("remarks"),
            snapshot=body.get("snapshot") or {},
            saved_by=str(body.get("saved_by", "info@cambiumretail.com")),
        )
        return {
            "status":     "saved",
            "week_start": ws.isoformat(),
            "label":      week_label(ws),
            "saved_at":   now_ist().isoformat(),
        }
    except Exception as e:
        print("⚠️ CB save-working error:", e)
        return {"status": "error", "error": str(e)}


# =========================
# WEEK META + LIST PAST SAVED WEEKS
# =========================
@router.get("/saved-weeks")
def cb_saved_weeks():
    try:
        cb_replenishment_saved.ensure_table()
        saved = cb_replenishment_saved.list_saved_weeks()
    except Exception as e:
        print("⚠️ CB saved-weeks error:", e)
        saved = []

    ws = current_working_week_start()
    current = {
        "week_start": ws.isoformat(),
        "week_end":   week_end(ws).isoformat(),
        "label":      week_label(ws),
        "locked":     is_week_locked(ws),
    }

    for w in saved:
        wd = _date.fromisoformat(w["week_start"])
        w["week_end"] = week_end(wd).isoformat()
        w["label"]    = week_label(wd)

    return {"current_week": current, "saved_weeks": saved}


# =========================
# VIEW PAST WEEK (read only frozen snapshot)
# =========================
@router.get("/saved-week-data")
def cb_saved_week_data(week_start: str = Query(...)):
    try:
        cb_replenishment_saved.ensure_table()
        ws = _date.fromisoformat(week_start)
        rows = cb_replenishment_saved.load_week_snapshot(ws)
        return {
            "week_start": ws.isoformat(),
            "week_end":   week_end(ws).isoformat(),
            "label":      week_label(ws),
            "locked":     True,
            "rows":       rows,
        }
    except Exception as e:
        print("⚠️ CB saved-week-data error:", e)
        return {"week_start": week_start, "rows": [], "error": str(e)}


# =========================
# RESET API
# =========================
@router.post("/reset")
async def reset_cb_inputs():
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cb_inputs")
        conn.commit()
        conn.close()
        return {"status": "reset"}
    except Exception as e:
        print("CB RESET ERROR:", str(e))
        return {"status": "error", "error": str(e)}
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cb_inputs (
                model TEXT PRIMARY KEY,
                po_requirement INTEGER DEFAULT 0,
                remarks TEXT DEFAULT ''
            )
        """)
        cursor.execute("ALTER TABLE cb_inputs ADD COLUMN IF NOT EXISTS po_requirement INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE cb_inputs ADD COLUMN IF NOT EXISTS remarks TEXT DEFAULT ''")
        conn.commit()

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
