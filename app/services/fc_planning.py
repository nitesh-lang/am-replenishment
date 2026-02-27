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

def load_fc_data(account: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load raw shipments + ledger data.
    Includes safety validation.
    """
    if account.lower() == "nexlev":
        shipments_file = DATA_DIR / "fba_shipments_nexlev.csv"
        ledger_file = DATA_DIR / "inventory_ledger_nexlev.csv"
    elif account.lower() == "viomi":
        shipments_file = DATA_DIR / "fba_shipments_viomi.csv"
        ledger_file = DATA_DIR / "inventory_ledger_viomi.csv"
    else:
        raise ValueError("Invalid account selected")
    if not shipments_file.exists():
        raise FileNotFoundError(f"Missing file: {shipments_file}")

    if not ledger_file.exists():
        raise FileNotFoundError(f"Missing file: {ledger_file}")

    shipments = pd.read_csv(shipments_file)
    ledger = pd.read_csv(ledger_file)

    shipments.columns = shipments.columns.str.strip()
    ledger.columns = ledger.columns.str.strip()

    return shipments, ledger


# =================================================
# FC PLANNING ENGINE
# =================================================

def calculate_fc_plan(
    replenish_weeks: int = 8,
    channel: str = "All",
    account: str = "Nexlev"
) -> pd.DataFrame:
    """
    FC-Level Planning Engine

    Core Logic:
    -------------------------------------------------
    1. Load shipments (last 30 days)
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
    
    print("ACCOUNT:", account)
    print("SHIPMENTS ROWS:", len(shipments))
    print("LEDGER ROWS:", len(ledger))
    print("SHIPMENT SKUS SAMPLE:",
      shipments["Merchant SKU"].astype(str).str.upper().unique()[:5])

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
    # FILTER LAST 30 DAYS
    # =================================================

    last_date = shipments["Shipment Date"].max()

    if pd.isna(last_date):
        raise ValueError("Shipment Date column contains no valid dates.")

    cutoff_date = last_date - pd.Timedelta(days=30)

    shipments_30 = shipments[
        shipments["Shipment Date"] >= cutoff_date
    ].copy()
    
    print("SHIPMENTS LAST 30 DAYS:", len(shipments_30))
    print("MAX DATE IN FILE:", last_date)
    # =================================================
    # SALES CHANNEL FILTER
    # =================================================

    if channel.lower() != "all":
     shipments_30 = shipments_30[
        shipments_30["Sales Channel"] == channel.strip().lower()
    ].copy()
    
    print("AFTER CHANNEL FILTER:", len(shipments_30))
    print("CHANNEL SELECTED:", channel)
    print("UNIQUE CHANNELS:", shipments_30["Sales Channel"].unique())

    shipments_30["sku"] = shipments_30["sku"].astype(str).str.strip().str.upper()

    # =================================================
    # FC VELOCITY CALCULATION
    # =================================================

    fc_velocity = (
        shipments_30
        .groupby(["sku", "FC"], as_index=False)
        .agg(total_units_30d=("Shipped Quantity", "sum"))
    )
    
    print("FC VELOCITY ROWS:", len(fc_velocity))
    print("SAMPLE VELOCITY:", fc_velocity.head())

    fc_velocity["FC"] = fc_velocity["FC"].astype(str).str.strip().str.upper()

    # Convert 30-day to weekly velocity
    fc_velocity["weekly_velocity"] = (
        fc_velocity["total_units_30d"] / 4.285
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
    
    print("LEDGER ROWS:", len(fc_inventory))
    print("SAMPLE LEDGER:", fc_inventory.head())

    print("UNIQUE FC IN VELOCITY:", fc_velocity["FC"].unique()[:10])
    print("UNIQUE LOCATION IN LEDGER:", fc_inventory["Location"].unique()[:10])
    # =================================================
    # MERGE VELOCITY + INVENTORY
    # =================================================

    df = fc_velocity.merge(
        fc_inventory,
        left_on=["sku", "FC"],
        right_on=["MSKU", "Location"],
        how="left",
    )
     
    print("AFTER LEDGER MERGE ROWS:", len(df))
    print("NULL FC INVENTORY COUNT:", df["fc_inventory"].isna().sum())
    print("ROWS WHERE INVENTORY NULL:")
    print(df[df["fc_inventory"].isna()][["sku","FC"]].head(20))

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

    final_df = df[[
        "sku",
        "fulfillment_center",
        "total_units_30d",
        "weekly_velocity",
        "fc_inventory",
        "required_units",
        "fc_shortfall",
        "coverage_weeks",
        "excess_inventory",
    ]].copy()

    numeric_cols = [
        "total_units_30d",
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

    return final_df