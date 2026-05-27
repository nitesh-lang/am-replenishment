from fastapi import APIRouter, Query
from typing import Optional, List
import pandas as pd
import os
from app.services.china_reorder import china_reorder_logic

router = APIRouter(prefix="/china-reorder", tags=["China Reorder"])


@router.get("/")
def get_china_reorder(
    brand: List[str] = Query(..., description="One or more brand names — repeat the query param to pass multiple"),
    months: int = Query(3, ge=1, le=6, description="Planning horizon in months"),
    channel: str = Query("All", description="Sales channel filter"),
    from_week: Optional[int] = Query(default=None),
    to_week:   Optional[int] = Query(default=None),
):
    # Run the per-brand pipeline for each selected brand and concatenate.
    combined: list = []
    for b in brand:
        b = (b or "").strip()
        if not b:
            continue
        try:
            rows = china_reorder_logic(b, months, channel, from_week, to_week) or []
            # Stamp the brand on each row so multi-brand results are distinguishable
            for r in rows:
                r["brand"] = b
            combined.extend(rows)
        except ValueError as e:
            # Unknown brand — skip silently rather than fail the whole multi-brand request
            print(f"⚠️ china_reorder: skipped brand {b!r}: {e}")
            continue

    # available_weeks: union across all selected brands (sales file is shared)
    try:
        BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sales_path = os.path.join(BASE_DIR, "..", "data", "input", "weekly_sales_snapshot.csv")
        raw = pd.read_csv(sales_path)
        raw.columns = raw.columns.str.strip().str.lower()
        raw["brand"] = raw["brand"].astype(str).str.strip().str.lower()
        wanted = {b.strip().lower() for b in brand if b}
        raw = raw[raw["brand"].isin(wanted)]
        raw["week_num"] = raw["week"].astype(str).str.extract(r"(\d+)")[0].pipe(pd.to_numeric, errors="coerce")
        available_weeks = sorted(raw["week_num"].dropna().unique().tolist(), reverse=True)[:12]
        available_weeks = sorted([int(w) for w in available_weeks])
    except Exception:
        available_weeks = []

    return {"data": combined, "available_weeks": available_weeks}