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
from pathlib import Path
import json
import pandas as pd

from app.services.db import get_conn


def _cb_soh_synced_date() -> str:
    """Return the SnapshotDate the SP-API CB SOH was last pulled for.

    Reads the SnapshotDate column from data/input/vendor_soh_audio_array.csv
    (every row carries the same date — Amazon's vendor inventory report is a
    single-day snapshot). Falls back to "" when the file isn't present (eg
    the operator hasn't run scripts/sp_vendor_soh_pull.py yet).
    """
    p = Path("data/input/vendor_soh_audio_array.csv")
    if not p.exists():
        return ""
    try:
        df = pd.read_csv(p, usecols=["SnapshotDate"], nrows=5)
        s = df["SnapshotDate"].dropna().astype(str)
        s = s[s != ""]
        return str(s.iloc[0]) if not s.empty else ""
    except Exception:
        return ""

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
    velocity_mode: str = Query(
        default="max",
        description='"max" = max(selected window, last-2wk) [default]; '
                    '"window" = selected window only',
    ),
):

    try:
        df = load_cb_replenishment(
            from_week=from_week,
            to_week=to_week,
            cover_weeks=cover_weeks,
            velocity_mode=velocity_mode,
        )

        print(f"CB REPLENISHMENT ROWS: {len(df)} | window: {from_week}→{to_week} | cover: {cover_weeks}w")

        if df is None or df.empty:
            return {
                "data": [],
                "total_models": 0,
                "message": "No data returned from service"
            }

        # ✅ FETCH SAVED DATA FROM DB
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT model, po_requirement, remarks FROM cb_inputs")
                saved_data = cursor.fetchall()

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
        # Ensure is_eol exists on the df even if the master hasn't been updated yet
        if "is_eol" not in df.columns:
            df["is_eol"] = False

        response_df = df[[
            "brand",
            "model",
            "asin",
            "sku",
            "is_eol",
            "china_in_transit",
            "final_cb_qty",
            "ampm_inventory",
            "cb_3m_sales",
            "cambium_3m_sales",
            "avg_weekly_sales",
            "last_2_velocity",
            "velocity_basis",
            "estimated_qty",
            "deficiency",
            "open_po",
            "in_transit",
            "po_requirement",
            "buffer_note",
            "working_value",
            "remarks",
            "hazmat_type"
        ]].copy()
        response_df["is_eol"] = response_df["is_eol"].fillna(False).astype(bool)

        # Master column "Hazmat Type" is actually ASIN Sort Details
        response_df = response_df.rename(columns={"hazmat_type": "asin_sort_details"})

        for col in ["avg_weekly_sales", "last_2_velocity", "estimated_qty", "deficiency", "cb_3m_sales", "cambium_3m_sales"]:
            if col in response_df.columns:
                response_df[col] = response_df[col].round(0).astype(int)

        # Get last 12 available weeks for frontend dropdowns
        try:
            raw_sales = pd.read_csv("data/input/weekly_sales_snapshot.csv")
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
            "available_weeks": available_weeks,
            "cb_soh_synced_date": _cb_soh_synced_date(),
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
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM cb_inputs")
            conn.commit()
        return {"status": "reset"}
    except Exception as e:
        print("CB RESET ERROR:", str(e))
        return {"status": "error", "error": str(e)}
