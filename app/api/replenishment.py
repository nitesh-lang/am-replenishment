from fastapi import APIRouter, Query, Request
from app.services.replenishment import calculate_replenishment
from app.services.fc_final_allocation import calculate_final_allocation
from app.services.fc_planning import calculate_fc_plan, load_fc_data
from app.services.validation_engine import run_full_validation
import psycopg2
import os
import json


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
    sales_window: int = Query(default=4, ge=1),
    replenish_weeks: int = Query(default=8, ge=1),
    account: str = Query(default="NEXLEV"),
):
    df = calculate_replenishment(
        sales_window=sales_window,
        replenish_weeks=replenish_weeks,
        account=account
    )

    response = []

    for _, row in df.iterrows():

        # IXD Logic
        haz = str(row.get("Hazmat/non-Hazmat", "")).strip()
        ixd_type = "Non-IXD" if haz == "Non-IXD Non Hazmat" else "IXD"

        response.append({
            "model": row["model"],
            "category": str(row["Category"]) if row.get("Category") == row.get("Category") else "",
            "asin": str(row["ASIN"]) if row["ASIN"] == row["ASIN"] else "",
            "sku": str(row["SKU"]) if row["SKU"] == row["SKU"] else "",
            "listing_status": str(row["listing_status"]) if row.get("listing_status") == row.get("listing_status") else "-",
            "master_carton": int(row["Master Carton"]) if row.get("Master Carton") == row.get("Master Carton") else 0,
            "sales_velocity": int(row["sales_velocity"]),
            "total_units_sold": int(row["total_units_sold"]),
            "amazon_inventory": int(row["amazon_inventory"]),
            "inbound_inventory": int(row["inbound_inventory"]),
            "ampm_inventory": int(row["ampm_inventory"]),
            "required_units": int(row["required_units"]),
            "replenishment_qty": int(row["replenishment_qty"]),
            "warehouse_shortfall": int(row["warehouse_shortfall"]),
            "is_risky": bool(row["is_risky"]),
            "is_overstock": bool(row["is_overstock"]),
            "ixd_type": ixd_type,
            "hazmat_type": str(row["Hazmat Type"]) if row.get("Hazmat Type") else "",
            # ── Master Carton Intelligence (NEW) ──────────────────────────
            # recommended_qty : replenishment_qty rounded up to nearest
            #                     full carton (IXD = mandatory, Non-IXD = advisory)
            # carton_break_flag : True when excess > 50 % of one carton
            #                     → breaking the carton is the smarter move
            # cartons_needed    : how many full cartons that equals
            # excess_units      : units above raw requirement in full-carton scenario
            "recommended_qty": int(row.get("recommended_qty", row["replenishment_qty"])),
            "carton_break_flag": bool(row.get("carton_break_flag", False)),
            "cartons_needed": int(row.get("cartons_needed", 0)),
            "excess_units": int(row.get("excess_units", 0)),
        })

    return response


# =================================================
# FC FINAL ALLOCATION ENDPOINT
# =================================================
@router.get("/fc-final-allocation")
def get_fc_final(
    replenish_weeks: int = Query(default=8, ge=1),
    channel: str = Query(default="All"),
    account: str = Query(default="NEXLEV"),
):
    df = calculate_final_allocation(
        replenish_weeks=replenish_weeks,
        channel=channel,
        account=account
    )

    # ── Fossil: merge saved PO requirement + remarks from DB ──
    if account.lower() == "fossil":
        try:
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            cursor = conn.cursor()
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
            cursor.execute("SELECT sku, fulfillment_center, po_requirement, master_carton, remarks FROM fossil_fc_inputs")
            saved = cursor.fetchall()
            conn.close()

            if saved:
                import pandas as pd
                saved_df = pd.DataFrame(saved, columns=["sku", "fulfillment_center", "po_requirement_db", "master_carton_db", "remarks_db"])
                df = df.merge(saved_df, on=["sku", "fulfillment_center"], how="left")
                df["send_qty"]      = df["po_requirement_db"].fillna(df["send_qty"])
                df["master_carton"] = df["master_carton_db"].fillna(24).astype(int).astype(str)
                df["remarks"]       = df["remarks_db"].fillna("")
                df.drop(columns=["po_requirement_db", "master_carton_db", "remarks_db"], inplace=True)
            else:
                df["remarks"] = ""
                df["master_carton"] = "24"

        except Exception as e:
            print("⚠️ Fossil FC DB merge error:", e)
            df["remarks"] = ""
            df["master_carton"] = "24"

    return df.to_dict(orient="records")


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

        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cursor = conn.cursor()

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

        for row in data:
            sku               = str(row.get("sku", "")).strip().upper()
            fc                = str(row.get("fulfillment_center", "")).strip().upper()
            po_requirement    = int(row.get("po_requirement", 0))
            master_carton     = int(row.get("master_carton", 24))
            remarks           = str(row.get("remarks", ""))

            cursor.execute("""
                INSERT INTO fossil_fc_inputs (sku, fulfillment_center, po_requirement, master_carton, remarks)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (sku, fulfillment_center)
                DO UPDATE SET
                    po_requirement = EXCLUDED.po_requirement,
                    master_carton  = EXCLUDED.master_carton,
                    remarks        = EXCLUDED.remarks;
            """, (sku, fc, po_requirement, master_carton, remarks))

        conn.commit()
        conn.close()
        return {"status": "saved", "rows": len(data)}

    except Exception as e:
        print("⚠️ Fossil FC save error:", e)
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


# =================================================
# REPLENISHMENT ENDPOINT
# =================================================
@router.get("/replenishment")
def get_replenishment(
    sales_window: int = Query(default=4, ge=1),
    replenish_weeks: int = Query(default=8, ge=1),
    account: str = Query(default="NEXLEV"),
):
    df = calculate_replenishment(
        sales_window=sales_window,
        replenish_weeks=replenish_weeks,
        account=account
    )

    response = []

    for _, row in df.iterrows():

        # IXD Logic
        haz = str(row.get("Hazmat/non-Hazmat", "")).strip()
        ixd_type = "Non-IXD" if haz == "Non-IXD Non Hazmat" else "IXD"

        response.append({
            "model": row["model"],
            "category": str(row["Category"]) if row.get("Category") == row.get("Category") else "",
            "asin": str(row["ASIN"]) if row["ASIN"] == row["ASIN"] else "",
            "sku": str(row["SKU"]) if row["SKU"] == row["SKU"] else "",
            "listing_status": str(row["listing_status"]) if row.get("listing_status") == row.get("listing_status") else "-",
            "master_carton": int(row["Master Carton"]) if row.get("Master Carton") == row.get("Master Carton") else 0,
            "sales_velocity": int(row["sales_velocity"]),
            "total_units_sold": int(row["total_units_sold"]),
            "amazon_inventory": int(row["amazon_inventory"]),
            "inbound_inventory": int(row["inbound_inventory"]),
            "ampm_inventory": int(row["ampm_inventory"]),
            "required_units": int(row["required_units"]),
            "replenishment_qty": int(row["replenishment_qty"]),
            "warehouse_shortfall": int(row["warehouse_shortfall"]),
            "is_risky": bool(row["is_risky"]),
            "is_overstock": bool(row["is_overstock"]),
            "ixd_type": ixd_type,
            "hazmat_type": str(row["Hazmat Type"]) if row.get("Hazmat Type") else "",
            # ── Master Carton Intelligence (NEW) ──────────────────────────
            # recommended_qty : replenishment_qty rounded up to nearest
            #                     full carton (IXD = mandatory, Non-IXD = advisory)
            # carton_break_flag : True when excess > 50 % of one carton
            #                     → breaking the carton is the smarter move
            # cartons_needed    : how many full cartons that equals
            # excess_units      : units above raw requirement in full-carton scenario
            "recommended_qty": int(row.get("recommended_qty", row["replenishment_qty"])),
            "carton_break_flag": bool(row.get("carton_break_flag", False)),
            "cartons_needed": int(row.get("cartons_needed", 0)),
            "excess_units": int(row.get("excess_units", 0)),
        })

    return response


# =================================================
# FC FINAL ALLOCATION ENDPOINT
# =================================================
@router.get("/fc-final-allocation")
def get_fc_final(
    replenish_weeks: int = Query(default=8, ge=1),
    channel: str = Query(default="All"),
    account: str = Query(default="NEXLEV"),
):
    df = calculate_final_allocation(
        replenish_weeks=replenish_weeks,
        channel=channel,
        account=account
    )

    return df.to_dict(orient="records")


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