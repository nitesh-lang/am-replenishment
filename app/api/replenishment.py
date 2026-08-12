from fastapi import APIRouter, Query, Request
from app.services.replenishment import calculate_replenishment
from app.services.fc_final_allocation import calculate_final_allocation
from app.services.fc_planning import calculate_fc_plan, load_fc_data, count_available_fba_weeks, list_available_fba_weeks
from app.services.validation_engine import run_full_validation
from app.services import replenishment_saved
from app.services.week_helper import (
    current_working_week_start,
    week_end,
    week_label,
    is_week_locked,
    now_ist,
)
from datetime import date as _date
import json
import pandas as pd

from app.services.db import get_conn


# =================================================
# ROUTER SETUP
# =================================================
router = APIRouter(
    prefix="",
    tags=["replenishment"],
)


# =================================================
# REPLENISHMENT ENDPOINT
# =================================================
@router.get("/replenishment")
def get_replenishment(
    sales_window: int = Query(default=12, ge=1),
    replenish_weeks: int = Query(default=8, ge=1),
    account: str = Query(default="NEXLEV"),
):
    df = calculate_replenishment(
        sales_window=sales_window,
        replenish_weeks=replenish_weeks,
        account=account
    )

    # Merge in saved working_value for the current working week.
    saved_map = {}
    try:
        replenishment_saved.ensure_table()
        saved_map = replenishment_saved.load_working_value_map(
            account.strip().upper(),
            current_working_week_start(),
        )
    except Exception as e:
        print("⚠️ Could not load saved working values:", e)

    response = []

    for _, row in df.iterrows():

        # IXD Logic — Nexlev/Viomi have "Hazmat/non-Hazmat" column;
        # AA/WM have only "Hazmat Type" with values "IXD"/"NON IXD".
        # Any value containing a "NON IXD" token = Non-IXD. Substring
        # check (not exact) so "NON IXD Hazmat" (still hazardous but
        # Non-IXD routable, e.g. MR-03) flags correctly.
        haz = str(row.get("Hazmat/non-Hazmat", "")).strip()
        typ = str(row.get("Hazmat Type", "")).strip().upper()
        if (haz == "Non-IXD Non Hazmat"
                or "NON IXD" in typ or "NON-IXD" in typ or "NONIXD" in typ):
            ixd_type = "Non-IXD"
        else:
            ixd_type = "IXD"

        sku = str(row["SKU"]).strip().upper() if row["SKU"] == row["SKU"] else ""

        response.append({
            "model": row["model"],
            "category": str(row["Category"]) if row.get("Category") == row.get("Category") else "",
            "asin": str(row["ASIN"]) if row["ASIN"] == row["ASIN"] else "",
            "sku": sku,
            "listing_status": str(row["listing_status"]) if row.get("listing_status") == row.get("listing_status") else "-",
            "master_carton": int(row["Master Carton"]) if row.get("Master Carton") == row.get("Master Carton") else 0,
            "sales_velocity": int(row["sales_velocity"]),
            "window_velocity": int(row.get("window_velocity", row["sales_velocity"])),
            "last_4_velocity": int(row.get("last_4_velocity", 0)),
            "last_2_velocity": int(row.get("last_2_velocity", 0)),
            "velocity_basis": str(row.get("velocity_basis", "window")),
            "total_units_sold": int(row["total_units_sold"]),
            "units_last_4w": int(row.get("units_last_4w", 0)),
            "units_last_2w": int(row.get("units_last_2w", 0)),
            "amazon_inventory": int(row["amazon_inventory"]),
            "fba_inv": int(row["fba_inv"]),
            "inbound_inventory": int(row["inbound_inventory"]),
            "real_am_inv": int(row.get("real_am_inv", 0) or 0),
            "real_am_inv_available": int(row.get("real_am_inv_available", 0) or 0),
            "afn_reserved": int(row.get("afn_reserved", 0) or 0),
            "ledger_at_fc": int(row.get("ledger_at_fc", 0) or 0),
            "ledger_in_transit": int(row.get("ledger_in_transit", 0) or 0),
            "ampm_inventory": int(row["ampm_inventory"]),
            # Model-level Mother WH sum — same for every ASIN of a shared
            # model so approver sees the actual pool. Calc still uses
            # per-ASIN ampm_inventory. AA-focused but populated for all
            # accounts (safe: single-ASIN models see identical numbers).
            "model_ampm_inventory": int(row.get("model_ampm_inventory", row["ampm_inventory"]) or 0),
            # CB SOH — Cambium's vendor warehouse stock. AA only (populated
            # from CB Replenishment's final_cb_qty per model). None on
            # accounts without 1P vendor inventory.
            "cb_soh": (int(row["cb_soh"]) if row.get("cb_soh") == row.get("cb_soh") and row.get("cb_soh") is not None else None),
            "b2b_inventory":  int(row.get("b2b_inventory", 0)),
            "required_units": int(row["required_units"]),
            "replenishment_qty": int(row["replenishment_qty"]),
            "warehouse_shortfall": int(row["warehouse_shortfall"]),
            "buffer_note": str(row.get("buffer_note", "") or ""),
            "oos_weeks_3m":   int(row.get("oos_weeks_3m", 0) or 0),
            "thin_weeks_3m":  int(row.get("thin_weeks_3m", 0) or 0),
            "lost_units_3m":  int(row.get("lost_units_3m", 0) or 0),
            "momentum_flag":  str(row.get("momentum_flag", "") or ""),
            "is_risky": bool(row["is_risky"]),
            "is_overstock": bool(row["is_overstock"]),
            "ixd_type": ixd_type,
            "hazmat_type": str(row["Hazmat Type"]) if row.get("Hazmat Type") else "",
            "recommended_qty": int(row.get("recommended_qty", row["replenishment_qty"])),
            "carton_break_flag": bool(row.get("carton_break_flag", False)),
            "cartons_needed": int(row.get("cartons_needed", 0)),
            "excess_units": int(row.get("excess_units", 0)),
            "working_value": (saved_map.get(sku) or {}).get("working_value", ""),
            "remarks":       (saved_map.get(sku) or {}).get("remarks", ""),
            "weekly_sales":  list(row.get("weekly_sales", []) or []),
            "weekly_window": list(row.get("weekly_window", []) or []),
        })

    return response


# =================================================
# REPLENISHMENT — WEEK META + SAVED WEEKS
# =================================================
@router.get("/replenishment/saved-weeks")
def get_replenishment_saved_weeks(account: str = Query(default="NEXLEV")):
    account = account.strip().upper()
    try:
        replenishment_saved.ensure_table()
        saved = replenishment_saved.list_saved_weeks(account)
    except Exception as e:
        print("⚠️ Could not list saved weeks:", e)
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


# =================================================
# REPLENISHMENT — VIEW PAST WEEK SNAPSHOT (read only)
# =================================================
@router.get("/replenishment/saved-week-data")
def get_replenishment_saved_week_data(
    account: str = Query(default="NEXLEV"),
    week_start: str = Query(...),
):
    try:
        replenishment_saved.ensure_table()
        ws = _date.fromisoformat(week_start)
        rows = replenishment_saved.load_week_snapshot(account.strip().upper(), ws)
        return {
            "week_start": ws.isoformat(),
            "week_end":   week_end(ws).isoformat(),
            "label":      week_label(ws),
            "locked":     True,
            "rows":       rows,
        }
    except Exception as e:
        print("⚠️ Replenishment saved week load error:", e)
        return {"week_start": week_start, "rows": [], "error": str(e)}


# =================================================
# REPLENISHMENT — SAVE CURRENT WEEK
# =================================================
@router.post("/replenishment/save")
async def save_replenishment_week(request: Request):
    try:
        body = await request.json()
        account = str(body.get("account", "NEXLEV")).strip().upper()
        rows = body.get("rows", []) or []
        saved_by = str(body.get("saved_by", "info@cambiumretail.com"))

        ws = current_working_week_start()
        if is_week_locked(ws):
            return {
                "status": "locked",
                "error":  f"Working week ({week_label(ws)}) is past Saturday 11:59 PM IST. Cannot save.",
                "week_start": ws.isoformat(),
            }

        replenishment_saved.ensure_table()
        n = replenishment_saved.save_rows(account, ws, rows, saved_by)

        return {
            "status":     "saved",
            "rows":       n,
            "week_start": ws.isoformat(),
            "label":      week_label(ws),
            "saved_at":   now_ist().isoformat(),
        }
    except Exception as e:
        print("⚠️ Replenishment save error:", e)
        return {"status": "error", "error": str(e)}


# =================================================
# FC FINAL ALLOCATION ENDPOINT
# =================================================
@router.get("/fc-final-allocation")
def get_fc_final(
    replenish_weeks: int = Query(default=8, ge=1),
    channel: str = Query(default="All"),
    account: str = Query(default="NEXLEV"),
    sales_window: int = Query(default=12, ge=1, le=52),
    from_week: int | None = Query(default=None, ge=1, le=53),
    to_week:   int | None = Query(default=None, ge=1, le=53),
):
    df = calculate_final_allocation(
        replenish_weeks=replenish_weeks,
        channel=channel,
        account=account,
        sales_window=sales_window,
        from_week=from_week,
        to_week=to_week,
    )

    # ── Fossil: load remarks + master_carton from DB only, send_qty always fresh ──
    if account.lower() == "fossil":
        try:
            with get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS fossil_fc_inputs (
                            sku TEXT,
                            fulfillment_center TEXT,
                            po_requirement INTEGER DEFAULT 0,
                            master_carton INTEGER DEFAULT 24,
                            remarks TEXT DEFAULT '',
                            PRIMARY KEY (sku, fulfillment_center)
                        )
                    """)
                    conn.commit()

                    # Load only remarks from DB — master_carton always from input sheet/default
                    cursor.execute("SELECT sku, fulfillment_center, remarks FROM fossil_fc_inputs")
                    saved = cursor.fetchall()

            if saved:
                saved_df = pd.DataFrame(saved, columns=["sku", "fulfillment_center", "remarks_db"])
                df = df.merge(saved_df, on=["sku", "fulfillment_center"], how="left")
                df["remarks"] = df["remarks_db"].fillna("")
                df.drop(columns=["remarks_db"], inplace=True)
            else:
                df["remarks"] = ""

            # ── Cluster mapping ──
            FC_CLUSTER = {
                "BLR5": "BLR", "BLR7": "BLR", "BLR8": "BLR",
                "BOM4": "BOM", "BOM5": "BOM", "BOM7": "BOM",
                "AMD2": "BOM", "PNQ3": "BOM", "ISK3": "BOM",
                "MAA4": "TN",  "CJB1": "TN",
                "DEL2": "DEL", "DEL4": "DEL", "DEL5": "DEL",
                "DED3": "DEL", "DED4": "DEL", "LKO1": "DEL",
                "HYD3": "TEL", "HYD8": "TEL",
                "CCX1": "WB",
            }
            df["cluster"] = df["fulfillment_center"].str.upper().map(FC_CLUSTER).fillna("-")

            # cluster in-transit = sum of in_transit_qty per model+cluster
            cluster_it = (
                df.groupby(["model", "cluster"])["in_transit_qty"]
                .sum()
                .reset_index()
                .rename(columns={"in_transit_qty": "cluster_in_transit"})
            )
            df = df.merge(cluster_it, on=["model", "cluster"], how="left")
            df["cluster_in_transit"] = df["cluster_in_transit"].fillna(0).astype(int)

            # cluster open PO = sum of open_po_qty per model+cluster
            cluster_op = (
                df.groupby(["model", "cluster"])["open_po_qty"]
                .sum()
                .reset_index()
                .rename(columns={"open_po_qty": "cluster_open_po"})
            )
            df = df.merge(cluster_op, on=["model", "cluster"], how="left")
            df["cluster_open_po"] = df["cluster_open_po"].fillna(0).astype(int)

            # cluster SOH = sum of fc_inventory per model+cluster
            cluster_soh = (
                df.groupby(["model", "cluster"])["fc_inventory"]
                .sum()
                .reset_index()
                .rename(columns={"fc_inventory": "cluster_soh"})
            )
            df = df.merge(cluster_soh, on=["model", "cluster"], how="left")
            df["cluster_soh"] = df["cluster_soh"].fillna(0)

            # cluster target = sum of target_cover_units per model+cluster
            cluster_target = (
                df.groupby(["model", "cluster"])["target_cover_units"]
                .sum()
                .reset_index()
                .rename(columns={"target_cover_units": "cluster_target"})
            )
            df = df.merge(cluster_target, on=["model", "cluster"], how="left")
            df["cluster_target"] = df["cluster_target"].fillna(0)

            # cluster PO = max(0, cluster_target - cluster_soh - cluster_in_transit - cluster_open_po)
            # This nets existing SOH + in-transit + open PO across ALL FCs in cluster against combined target
            df["cluster_po_calc"] = (
                df["cluster_target"] - df["cluster_soh"] - df["cluster_in_transit"] - df["cluster_open_po"]
            ).clip(lower=0).round(0).astype(int)

            # Drop helper columns
            df.drop(columns=["cluster_soh", "cluster_target"], inplace=True)

            # load saved cluster PO overrides — only use DB value if it differs from calc
            # (i.e. user deliberately edited it)
            with get_conn() as conn2:
                with conn2.cursor() as cursor2:
                    cursor2.execute("""
                        CREATE TABLE IF NOT EXISTS fossil_cluster_po (
                            sku TEXT,
                            cluster TEXT,
                            cluster_po INTEGER DEFAULT 0,
                            PRIMARY KEY (sku, cluster)
                        )
                    """)
                    conn2.commit()
                    cursor2.execute("SELECT sku, cluster, cluster_po FROM fossil_cluster_po")
                    cluster_saved = cursor2.fetchall()

            # Always default to fresh calc; only use DB if it was manually overridden
            df["cluster_po"] = df["cluster_po_calc"].fillna(0).astype(int)
            df.drop(columns=["cluster_po_calc"], inplace=True)

        except Exception as e:
            print("⚠️ Fossil FC DB merge error:", e)
            df["remarks"] = ""
            df["master_carton"] = "24"
            df["cluster"] = "-"
            df["cluster_po"] = 0

    # Sort by model+cluster before blanking
    if "model" in df.columns and "cluster" in df.columns:
        df = df.sort_values(["model", "cluster", "fulfillment_center"]).reset_index(drop=True)

    # cluster_po and cluster_in_transit: only show on first FC row per model+cluster
    if "cluster_po" in df.columns and "cluster_in_transit" in df.columns:
        df["cluster_po"] = pd.to_numeric(df["cluster_po"], errors="coerce").fillna(0).astype(int)
        df["cluster_in_transit"] = pd.to_numeric(df["cluster_in_transit"], errors="coerce").fillna(0).astype(int)
        df["cluster_po"] = df["cluster_po"].astype(object)
        df["cluster_in_transit"] = df["cluster_in_transit"].astype(object)
        df["_rank"] = df.groupby(["model", "cluster"]).cumcount()
        df.loc[df["_rank"] > 0, "cluster_po"] = "BLANK"
        df.loc[df["_rank"] > 0, "cluster_in_transit"] = "BLANK"
        df.drop(columns=["_rank"], inplace=True)

    # ── Non-Fossil accounts: merge saved per-row Working Value + Remarks
    # from fc_allocation_inputs (parallel to Fossil's fossil_fc_inputs).
    # Keyed on (account, sku, fulfillment_center). Naresh types these in
    # the UI; auto-saves on blur.
    if account.lower() != "fossil":
        try:
            with get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS fc_allocation_inputs (
                            account TEXT NOT NULL,
                            sku TEXT NOT NULL,
                            fulfillment_center TEXT NOT NULL,
                            working_value TEXT DEFAULT '',
                            remarks TEXT DEFAULT '',
                            saved_at TIMESTAMPTZ DEFAULT NOW(),
                            saved_by TEXT,
                            PRIMARY KEY (account, sku, fulfillment_center)
                        )
                    """)
                    cursor.execute(
                        "SELECT sku, fulfillment_center, working_value, remarks FROM fc_allocation_inputs WHERE account = %s",
                        (account.strip().upper(),),
                    )
                    saved = {(s, fc): (wv or "", rk or "") for s, fc, wv, rk in cursor.fetchall()}
            if saved:
                df["working_value"] = df.apply(
                    lambda r: saved.get(
                        (str(r["sku"]).strip().upper(), str(r["fulfillment_center"]).strip().upper()),
                        ("", ""),
                    )[0],
                    axis=1,
                )
                df["remarks"] = df.apply(
                    lambda r: saved.get(
                        (str(r["sku"]).strip().upper(), str(r["fulfillment_center"]).strip().upper()),
                        ("", ""),
                    )[1],
                    axis=1,
                )
            else:
                df["working_value"] = ""
                if "remarks" not in df.columns:
                    df["remarks"] = ""
        except Exception as _e:
            print(f"⚠️ fc_allocation_inputs merge failed: {_e}")
            df["working_value"] = ""
            if "remarks" not in df.columns:
                df["remarks"] = ""

    # Replace NaN/inf with safe defaults before JSON serialization
    df = df.fillna("").replace([float("inf"), float("-inf")], 0)
    # Integer columns — quantities that should render whole numbers on the UI
    for col in ["in_transit_qty", "open_po_qty", "send_qty", "fc_inventory",
                "total_units_sold"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    # Velocity columns — preserve decimals so Avg/Wk × weeks matches the
    # actual target math (e.g. 6.5 * 6 = 39, NOT the "6 x 6 = 36" the
    # rounded-to-int display used to suggest). Rounded to 1 decimal for
    # compact display.
    for col in ["weekly_velocity", "window_velocity", "last_2_velocity"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).round(1)

    records = df.to_dict(orient="records")
    for r in records:
        if r.get("cluster_po") == "BLANK":
            r["cluster_po"] = None
        if r.get("cluster_in_transit") == "BLANK":
            r["cluster_in_transit"] = None
    return {
        "data": records,
        "available_weeks": list_available_fba_weeks(),
    }


# =================================================
# FOSSIL FC RESET ENDPOINT
# =================================================
@router.post("/fc-final-allocation/fossil-reset")
async def reset_fossil_fc_inputs():
    try:
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM fossil_fc_inputs")
                cursor.execute("DELETE FROM fossil_cluster_po")
            conn.commit()
        return {"status": "reset"}
    except Exception as e:
        print("⚠️ Fossil FC reset error:", e)
        return {"status": "error", "error": str(e)}


# =================================================
# FOSSIL FC SAVE ENDPOINT
# =================================================
@router.post("/fc-final-allocation/fossil-save")
async def save_fossil_fc_inputs(request: Request):
    try:
        data = await request.json()
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict):
            data = [data]

        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fossil_fc_inputs (
                        sku TEXT,
                        fulfillment_center TEXT,
                        po_requirement INTEGER DEFAULT 0,
                        remarks TEXT DEFAULT '',
                        PRIMARY KEY (sku, fulfillment_center)
                    )
                """)

                for row in data:
                    sku            = str(row.get("sku", "")).strip().upper()
                    fc             = str(row.get("fulfillment_center", "")).strip().upper()
                    po_requirement = int(row.get("po_requirement", 0))
                    remarks        = str(row.get("remarks", ""))

                    cursor.execute("""
                        INSERT INTO fossil_fc_inputs (sku, fulfillment_center, po_requirement, remarks)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (sku, fulfillment_center)
                        DO UPDATE SET
                            po_requirement = EXCLUDED.po_requirement,
                            remarks        = EXCLUDED.remarks;
                    """, (sku, fc, po_requirement, remarks))

            conn.commit()
        return {"status": "saved", "rows": len(data)}

    except Exception as e:
        print("⚠️ Fossil FC save error:", e)
        return {"status": "error", "error": str(e)}


# =================================================
# FC ALLOCATION per-row inputs — non-Fossil accounts
# (Nex / Viomi / AA / WM). Naresh types Working Value and Remarks;
# auto-saves on blur. Same pattern as fossil_fc_inputs but keyed on
# (account, sku, fc) so multiple accounts share the table cleanly.
# =================================================
@router.post("/fc-final-allocation/save-inputs")
async def save_fc_alloc_inputs(request: Request):
    try:
        data = await request.json()
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return {"status": "error", "error": "expected list of rows"}
        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fc_allocation_inputs (
                        account TEXT NOT NULL,
                        sku TEXT NOT NULL,
                        fulfillment_center TEXT NOT NULL,
                        working_value TEXT DEFAULT '',
                        remarks TEXT DEFAULT '',
                        saved_at TIMESTAMPTZ DEFAULT NOW(),
                        saved_by TEXT,
                        PRIMARY KEY (account, sku, fulfillment_center)
                    )
                """)
                for row in data:
                    account = str(row.get("account", "")).strip().upper()
                    sku     = str(row.get("sku", "")).strip().upper()
                    fc      = str(row.get("fulfillment_center", "")).strip().upper()
                    if not account or not sku or not fc:
                        continue
                    wv = row.get("working_value")
                    working_value = "" if wv is None else str(wv)
                    rk = row.get("remarks")
                    remarks = "" if rk is None else str(rk)
                    saved_by = str(row.get("saved_by", ""))
                    cursor.execute("""
                        INSERT INTO fc_allocation_inputs
                            (account, sku, fulfillment_center, working_value, remarks, saved_at, saved_by)
                        VALUES (%s, %s, %s, %s, %s, NOW(), %s)
                        ON CONFLICT (account, sku, fulfillment_center) DO UPDATE SET
                            working_value = EXCLUDED.working_value,
                            remarks       = EXCLUDED.remarks,
                            saved_at      = NOW(),
                            saved_by      = EXCLUDED.saved_by
                    """, (account, sku, fc, working_value, remarks, saved_by))
            conn.commit()
        return {"status": "saved", "rows": len(data)}
    except Exception as e:
        print("⚠️ FC alloc save-inputs error:", e)
        return {"status": "error", "error": str(e)}


# =================================================
# FOSSIL CLUSTER PO SAVE ENDPOINT
# =================================================
@router.post("/fc-final-allocation/fossil-cluster-save")
async def save_fossil_cluster_po(request: Request):
    try:
        data = await request.json()
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict):
            data = [data]

        with get_conn() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fossil_cluster_po (
                        sku TEXT,
                        cluster TEXT,
                        cluster_po INTEGER DEFAULT 0,
                        PRIMARY KEY (sku, cluster)
                    )
                """)

                for row in data:
                    sku        = str(row.get("sku", "")).strip().upper()
                    cluster    = str(row.get("cluster", "")).strip().upper()
                    cluster_po = int(row.get("cluster_po", 0))

                    cursor.execute("""
                        INSERT INTO fossil_cluster_po (sku, cluster, cluster_po)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (sku, cluster)
                        DO UPDATE SET cluster_po = EXCLUDED.cluster_po;
                    """, (sku, cluster, cluster_po))

            conn.commit()
        return {"status": "saved", "rows": len(data)}

    except Exception as e:
        print("⚠️ Fossil cluster PO save error:", e)
        return {"status": "error", "error": str(e)}


# =================================================
# FC VALIDATION ENDPOINT
# =================================================
@router.get("/fc-validation")
def fc_validation(
    replenish_weeks: int = Query(default=12, ge=1),
    channel: str = Query(default="All"),
    account: str = Query(default="NEXLEV"),
):
    shipments, ledger = load_fc_data(account)

    fc_plan_df = calculate_fc_plan(
        replenish_weeks=replenish_weeks,
        channel=channel,
        account=account
    )

    validation_report = run_full_validation(
        shipments,
        ledger,
        fc_plan_df
    )

    return validation_report