from app.services.validation_engine import run_full_validation
from app.services.file_cache import get, get_excel_sheet
import os
from sqlalchemy import create_engine
import pandas as pd
from pathlib import Path
from typing import Tuple

# =================================================
# CONFIGURATION
# =================================================

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "input"



# =================================================
# DATA LOADERS
# =================================================
def load_fc_data(account: str):

    # ── FOSSIL: load directly from CSV files, not DB ──
    if account.lower() == "fossil":
        fossil_dir = DATA_DIR / "Fossil Replenishment"
        shipments = pd.read_csv(fossil_dir / "fba_shipments_fossil.csv", low_memory=False)
        ledger    = pd.read_csv(fossil_dir / "inventory_ledger_fossil.csv", low_memory=False)
        shipments.columns = shipments.columns.str.strip()
        ledger.columns    = ledger.columns.str.strip()
        return shipments, ledger

    engine = create_engine(os.getenv("DATABASE_URL"))

    shipments = pd.read_sql(
        "SELECT * FROM shipments WHERE LOWER(account) = %s",
        engine,
        params=(account.lower(),)
    )

    ledger = pd.read_sql(
        "SELECT * FROM inventory_ledger WHERE LOWER(account) = %s",
        engine,
        params=(account.lower(),)
    )

    shipments.columns = shipments.columns.str.strip()
    ledger.columns    = ledger.columns.str.strip()

    return shipments, ledger


# =================================================
# FC PLANNING ENGINE
# =================================================

def calculate_fc_plan(
    replenish_weeks: int,
    channel: str,
    account: str
) -> pd.DataFrame:
    """
    FC-Level Planning Engine

    Core Logic:
    -------------------------------------------------
    1. Load shipments (last 90 days)
    2. Calculate FC velocity
    3. Load ledger ending balance
    4. Merge velocity + inventory
    5. Calculate required units
    6. Calculate shortfall
    7. Calculate coverage metrics
    8. Return structured output for UI transparency
    -------------------------------------------------
    """

    shipments, ledger = load_fc_data(account)

    # =================================================
    # VALIDATE SHIPMENTS STRUCTURE
    # =================================================

    required_ship_cols = [
        "Merchant SKU",
        "Shipped Quantity",
        "Shipment Date",
        "FC",
        "Sales Channel",
    ]

    for col in required_ship_cols:
        if col not in shipments.columns:
            raise ValueError(f"Missing column in shipments file: {col}")
        # Normalize SKU column (internal standard)
    shipments = shipments.rename(columns={"Merchant SKU": "sku"})
    shipments["Sales Channel"] = (
    shipments["Sales Channel"]
    .astype(str)
    .str.strip()
    .str.lower()
)
    shipments["sku"] = shipments["sku"].astype(str).str.strip().str.upper()

    shipments["Shipment Date"] = pd.to_datetime(
        shipments["Shipment Date"], errors="coerce"
    )

    shipments["Shipped Quantity"] = pd.to_numeric(
        shipments["Shipped Quantity"], errors="coerce"
    ).fillna(0)

    # =================================================
    # FILTER LAST 90 DAYS
    # =================================================

    last_date = shipments["Shipment Date"].max()

    if pd.isna(last_date):
        raise ValueError("Shipment Date column contains no valid dates.")

    cutoff_date = last_date - pd.Timedelta(days=90)

    shipments_90 = shipments[
        shipments["Shipment Date"] >= cutoff_date
    ].copy()
    
    # =================================================
    # SALES CHANNEL FILTER
    # =================================================

    if channel.lower() != "all":
     shipments_90 = shipments_90[
        shipments_90["Sales Channel"] == channel.strip().lower()
    ].copy()
    

    shipments_90["sku"] = shipments_90["sku"].astype(str).str.strip().str.upper()

    # =================================================
    # FC VELOCITY CALCULATION
    # =================================================

    fc_velocity = (
        shipments_90
        .groupby(["sku", "FC"], as_index=False)
        .agg(total_units_90d=("Shipped Quantity", "sum"))
    )
    

    fc_velocity["FC"] = fc_velocity["FC"].astype(str).str.strip().str.upper()

    # Convert 90-day to weekly velocity
    fc_velocity["weekly_velocity"] = (
        fc_velocity["total_units_90d"] / 12.857
    )

    fc_velocity["weekly_velocity"] = fc_velocity[
        "weekly_velocity"
    ].round(2)

    # =================================================
    # VALIDATE LEDGER STRUCTURE
    # =================================================

    required_ledger_cols = [
        "MSKU",
        "Location",
        "Ending Warehouse Balance", 
    ]

    for col in required_ledger_cols:
        if col not in ledger.columns:
            raise ValueError(f"Missing column in ledger file: {col}")

    ledger["Ending Warehouse Balance"] = pd.to_numeric(
        ledger["Ending Warehouse Balance"], errors="coerce"
    ).fillna(0)

    # Filter only SELLABLE inventory
    ledger = ledger[ledger["Disposition"] == "SELLABLE"].copy() 
    # =================================================
    # AGGREGATE LEDGER BY SKU + FC
    # =================================================
    ledger["MSKU"] = ledger["MSKU"].astype(str).str.strip().str.upper()
    ledger["Location"] = ledger["Location"].astype(str).str.strip().str.upper()
    fc_inventory = (
        ledger
        .groupby(["MSKU", "Location"], as_index=False)
        .agg(fc_inventory=("Ending Warehouse Balance", "sum"))
    )
    

    # =================================================
    # MERGE VELOCITY + INVENTORY
    # =================================================

    df = fc_velocity.merge(
        fc_inventory,
        left_on=["sku", "FC"],
        right_on=["MSKU", "Location"],
        how="left",
    )
     

    df["fc_inventory"] = df["fc_inventory"].fillna(0)

    # =================================================
    # REQUIRED UNITS (TARGET COVER)
    # =================================================

    df["required_units"] = (
        df["weekly_velocity"] * replenish_weeks
    ).round(2)

    # =================================================
    # FC SHORTFALL
    # =================================================

    df["fc_shortfall"] = (
        df["required_units"] - df["fc_inventory"]
    ).clip(lower=0).round(2)

    # =================================================
    # ADDITIONAL EXPLANATION METRICS (FOR UI)
    # =================================================

    # Coverage weeks at FC
    df["coverage_weeks"] = (
        df["fc_inventory"] / df["weekly_velocity"].replace(0, 1)
    ).round(2)

    # Excess inventory
    df["excess_inventory"] = (
        df["fc_inventory"] - df["required_units"]
    ).clip(lower=0).round(2)

    # =================================================
    # CLEAN & FINAL STRUCTURE
    # =================================================

    df = df.rename(columns={
    "FC": "fulfillment_center"
})
    
    # =========================
    # ADD MODEL MAPPING (FIX)
    # =========================

    if account.lower() == "nexlev":
        master_df = get("replenishment_master_nexlev.xlsx")
    elif account.lower() == "viomi":
        master_df = get("replenishment_master_viomi.xlsx")
    elif account.lower() == "white mulberry":
        master_df = get_excel_sheet("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "WM")
    elif account.lower() == "audio array":
        master_df = get_excel_sheet("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "AA")
    elif account.lower() == "fossil":
        master_df = get_excel_sheet("Fossil Replenishment/Fossil Replenishment.xlsx", "Sheet1")
        master_df.columns = master_df.columns.str.strip()
        master_df = master_df.rename(columns={"SKU": "sku", "Item No": "model"})
        master_df["sku"] = master_df["sku"].astype(str).str.strip().str.upper()
        final_df = df[["model", "sku", "fulfillment_center", "total_units_90d", "weekly_velocity",
                        "fc_inventory", "required_units", "fc_shortfall", "coverage_weeks", "excess_inventory"]].copy()
        for col in ["total_units_90d", "weekly_velocity", "fc_inventory", "required_units",
                    "fc_shortfall", "coverage_weeks", "excess_inventory"]:
            final_df[col] = pd.to_numeric(final_df[col], errors="coerce").fillna(0)
        df = df.merge(master_df[["sku", "model"]], on="sku", how="left")
        df["model"] = df.get("model_y", df.get("model", "-")).fillna("-")
        if "model_y" in df.columns:
            df.drop(columns=["model_y"], inplace=True)
        final_df = df[["model", "sku", "fulfillment_center", "total_units_90d", "weekly_velocity",
                        "fc_inventory", "required_units", "fc_shortfall", "coverage_weeks", "excess_inventory"]].copy()
        for col in ["total_units_90d", "weekly_velocity", "fc_inventory", "required_units",
                    "fc_shortfall", "coverage_weeks", "excess_inventory"]:
            final_df[col] = pd.to_numeric(final_df[col], errors="coerce").fillna(0)
        validation_report = run_full_validation(shipments_90, ledger, final_df)
        return final_df
    else:
        master_df = get("replenishment_master_nexlev.xlsx")

    master_df.columns = master_df.columns.str.strip()

    master_df = master_df.rename(columns={
            "SKU": "sku",
            "Model": "model"
})

    master_df["sku"] = master_df["sku"].astype(str).str.strip().str.upper()

    df = df.merge(master_df[["sku", "model"]], on="sku", how="left")

    final_df = df[[
        "model",
        "sku",
        "fulfillment_center",
        "total_units_90d",
        "weekly_velocity",
        "fc_inventory",
        "required_units",
        "fc_shortfall",
        "coverage_weeks",
        "excess_inventory",
    ]].copy()

    numeric_cols = [
        "total_units_90d",
        "weekly_velocity",
        "fc_inventory",
        "required_units",
        "fc_shortfall",
        "coverage_weeks",
        "excess_inventory",
    ]

    for col in numeric_cols:
        final_df[col] = pd.to_numeric(
            final_df[col], errors="coerce"
        ).fillna(0)


    validation_report = run_full_validation(
    shipments_90,
    ledger,
    final_df
)


    return final_df