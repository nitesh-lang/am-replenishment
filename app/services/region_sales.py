import pandas as pd
from pathlib import Path

# =================================================
# CONFIG
# =================================================
BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data" / "input"


# =================================================
# REGION SALES ENGINE (ACCOUNT + REGION WISE)
# =================================================
def calculate_region_sales(account: str = "Nexlev") -> pd.DataFrame:
    """
    Region Sales Engine

    Logic:
    1. Select shipment file based on account
    2. Load FBA shipments Excel file
    3. Filter last 30 days
    4. Group by SKU + Shipping State
    5. Calculate total units, weekly velocity, and revenue
    """

    # -------------------------------------------------
    # Select File Based on Account
    # -------------------------------------------------
    if account.lower() == "nexlev":
        shipments_file = DATA_DIR / "fba_shipments_nexlev.csv"
    else:
        shipments_file = DATA_DIR / "fba_shipments_viomi.csv"

    if not shipments_file.exists():
        raise FileNotFoundError(f"Missing file: {shipments_file}")

    # -------------------------------------------------
    # Load File (Excel)
    # -------------------------------------------------
    shipments = pd.read_csv(shipments_file)
    shipments.columns = shipments.columns.str.strip()

    # -------------------------------------------------
    # Required Columns Validation
    # -------------------------------------------------
    required_cols = [
        "Merchant SKU",
        "Shipped Quantity",
        "Shipment Date",
        "Shipping State",
        "Item Price",
    ]

    for col in required_cols:
        if col not in shipments.columns:
            raise ValueError(f"Missing column in shipments file: {col}")

    # -------------------------------------------------
    # Data Cleaning
    # -------------------------------------------------
    shipments["Shipment Date"] = pd.to_datetime(
        shipments["Shipment Date"], errors="coerce"
    )

    shipments["Shipped Quantity"] = pd.to_numeric(
        shipments["Shipped Quantity"], errors="coerce"
    ).fillna(0)

    shipments["Item Price"] = pd.to_numeric(
        shipments["Item Price"], errors="coerce"
    ).fillna(0)

    # Revenue Calculation
    shipments["Revenue"] = shipments["Item Price"]

    # -------------------------------------------------
    # Filter Last 30 Days
    # -------------------------------------------------
    last_date = shipments["Shipment Date"].max()

    if pd.isna(last_date):
        return pd.DataFrame()

    cutoff_date = last_date - pd.Timedelta(days=30)

    shipments_30 = shipments

    if shipments_30.empty:
        return pd.DataFrame()

    # -------------------------------------------------
    # Region Aggregation
    # -------------------------------------------------
    region_sales = (
        shipments_30
        .groupby(["Merchant SKU", "Shipping State"], as_index=False)
        .agg(
            total_units_30d=("Shipped Quantity", "sum"),
            revenue_30d=("Revenue", "sum"),
        )
    )

    # -------------------------------------------------
    # Weekly Velocity (30 days ≈ 4.285 weeks)
    # -------------------------------------------------
    region_sales["weekly_velocity"] = (
        region_sales["total_units_30d"] / 4.285
    )

    # -------------------------------------------------
    # Rename for Frontend Consistency
    # -------------------------------------------------
    region_sales = region_sales.rename(columns={
        "Merchant SKU": "sku",
        "Shipping State": "region"
    })

    return region_sales