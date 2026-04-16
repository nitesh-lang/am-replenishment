from app.services.validation_engine import run_full_validation
from app.services.file_cache import get, get_excel_sheet
import os
import pandas as pd


# =================================================
# FILE MAP — account → shipments + ledger files
# =================================================

ACCOUNT_FILES = {
    "nexlev": {
        "shipments": "fba_shipments_nexlev.csv",
        "ledger":    "inventory_ledger_nexlev.csv",
    },
    "viomi": {
        "shipments": "fba_shipments_viomi.csv",
        "ledger":    "inventory_ledger_viomi.csv",
    },
    "white mulberry": {
        "shipments": "fba_shipments_WM.csv",
        "ledger":    "inventory_ledger_WM.csv",
    },
    "audio array": {
        "shipments": "fba_shipments_Audio Array.csv",
        "ledger":    "inventory_ledger_Audio Array.csv",
    },
    "fossil": {
        "shipments": "Fossil Replenishment/fba_shipments_fossil.csv",
        "ledger":    "Fossil Replenishment/inventory_ledger_fossil.csv",
    },
}


# =================================================
# DATA LOADERS — reads directly from repo files
# =================================================
def load_fc_data(account: str):
    key = account.strip().lower()
    if key not in ACCOUNT_FILES:
        raise ValueError(f"Unknown account for FC data: {account}")

    files = ACCOUNT_FILES[key]
    shipments = get(files["shipments"]).copy()
    ledger    = get(files["ledger"]).copy()

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

    # Fossil SKUs use FBS/FBO/FBK prefixes in shipments but FBA in master — normalize
    if account.lower() == "fossil":
        shipments["sku"] = shipments["sku"].str.replace(r"^FB[^A]", "FBA", regex=True)

    shipments["Shipment Date"] = pd.to_datetime(
        shipments["Shipment Date"], errors="coerce"
    )

    shipments["Shipped Quantity"] = pd.to_numeric(
        shipments["Shipped Quantity"], errors="coerce"
    ).fillna(0)

    # =================================================
    # FILTER LAST 90 DAYS
    # =================================================

    last_date  = shipments["Shipment Date"].max()
    first_date = shipments["Shipment Date"].min()

    if pd.isna(last_date) or pd.isna(first_date):
        raise ValueError("Shipment Date column contains no valid dates.")

    total_days  = max((last_date - first_date).days + 1, 1)
    total_weeks = total_days / 7

    # Use ALL data in the file — no arbitrary cutoff
    # File should contain exactly the sales window you want (e.g. 90 days)
    shipments_90 = shipments.copy()

    # DEBUG — log key values for Fossil to verify file is fresh
    if account.lower() == "fossil":
        print(f"🔍 FC PLANNING DEBUG [{account}] replenish_weeks={replenish_weeks}")
        print(f"   Shipments total rows: {len(shipments)}")
        print(f"   File date range: {first_date.date()} → {last_date.date()} ({total_days} days / {total_weeks:.2f} weeks)")
        del5 = shipments[(shipments["sku"]=="FBA66963") & (shipments["FC"]=="DEL5")]
        print(f"   FBA66963/DEL5 units in file: {del5['Shipped Quantity'].sum()}")
        print(f"   FBA66963/DEL5 velocity: {del5['Shipped Quantity'].sum()/total_weeks:.2f}")
    
    # =================================================
    # SALES CHANNEL FILTER
    # =================================================

    if channel.lower() != "all":
     shipments_90 = shipments_90[
        shipments_90["Sales Channel"] == channel.strip().lower()
    ].copy()
    

    shipments_90["sku"] = shipments_90["sku"].astype(str).str.strip().str.upper()

    # Fossil: normalize FBS/FBO/FBK → FBA to match master file
    if account.lower() == "fossil":
        shipments_90["sku"] = shipments_90["sku"].str.replace(r"^FB[^A]", "FBA", regex=True)

    # =================================================
    # FC VELOCITY CALCULATION
    # =================================================

    fc_velocity = (
        shipments_90
        .groupby(["sku", "FC"], as_index=False)
        .agg(total_units_90d=("Shipped Quantity", "sum"))
    )
    

    fc_velocity["FC"] = fc_velocity["FC"].astype(str).str.strip().str.upper()

    # Convert total period to weekly velocity
    fc_velocity["weekly_velocity"] = (
        fc_velocity["total_units_90d"] / total_weeks
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

    # Fossil: normalize FBS/FBO/FBK → FBA to match master file
    if account.lower() == "fossil":
        ledger["MSKU"] = ledger["MSKU"].str.replace(r"^FB[^A]", "FBA", regex=True)
    fc_inventory = (
        ledger
        .groupby(["MSKU", "Location"], as_index=False)
        .agg(fc_inventory=("Ending Warehouse Balance", "sum"))
    )

    # DEBUG — log ledger values for Fossil
    if account.lower() == "fossil":
        del5_led = fc_inventory[(fc_inventory["MSKU"]=="FBA66963") & (fc_inventory["Location"]=="DEL5")]
        print(f"   Ledger total rows: {len(ledger)}")
        print(f"   FBA66963/DEL5 FC SOH: {del5_led['fc_inventory'].sum()}")
        del5_vel = fc_velocity[(fc_velocity["sku"]=="FBA66963") & (fc_velocity["FC"]=="DEL5")]
        if len(del5_vel):
            v = del5_vel['weekly_velocity'].values[0]
            soh = del5_led['fc_inventory'].sum()
            print(f"   FBA66963/DEL5 → velocity={v:.2f}, target_8w={v*8:.1f}, po_req_8w={max(0,v*8-soh):.1f}")
    

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
        # inner join — only keep SKUs that exist in the input master file
        df = df.merge(master_df[["sku", "model"]], on="sku", how="inner")
        if "model_y" in df.columns:
            df["model"] = df["model_y"].combine_first(df.get("model_x", pd.Series("-", index=df.index)))
            df.drop(columns=[c for c in ["model_x", "model_y"] if c in df.columns], inplace=True)
        elif "model" not in df.columns:
            df["model"] = "-"
        df["model"] = df["model"].fillna("-")
        final_df = df[[
            "model", "sku", "fulfillment_center", "total_units_90d", "weekly_velocity",
            "fc_inventory", "required_units", "fc_shortfall", "coverage_weeks", "excess_inventory"
        ]].copy()
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