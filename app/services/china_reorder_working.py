import pandas as pd
from pathlib import Path

# =====================================================
# PATH SETUP
# =====================================================

BASE_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = BASE_DIR / "data" / "input"

SALES_FILE = DATA_DIR / "weekly_sales_snapshot - ChinaReorder.csv"
INVENTORY_FILE = DATA_DIR / "inventory_model_snapshot_China Reoder.xlsx"


# =====================================================
# LOAD SALES SNAPSHOT
# =====================================================

def load_sales_snapshot():
    df = pd.read_csv(SALES_FILE)

    df.columns = df.columns.str.strip().str.lower()

    return df


# =====================================================
# LOAD INVENTORY SNAPSHOT
# =====================================================

def load_inventory_snapshot():
    df = pd.read_excel(INVENTORY_FILE)

    df.columns = df.columns.str.strip().str.lower()

    return df


# =====================================================
# MERGE SALES + INVENTORY
# =====================================================

def get_china_reorder_working_data(
    brand: str | None = None,
    channel: str | None = None,
    model: str | None = None,
):
    sales_df = load_sales_snapshot()
    inventory_df = load_inventory_snapshot()

    # -------------------------------
    # Merge on brand + model
    # -------------------------------
    merged_df = sales_df.merge(
        inventory_df,
        on=["brand", "model"],
        how="left",
        suffixes=("", "_inventory")
    )

    # -------------------------------
    # Filters
    # -------------------------------
    if brand:
        merged_df = merged_df[merged_df["brand"] == brand]

    if channel:
        merged_df = merged_df[merged_df["channel"] == channel]

    if model:
        merged_df = merged_df[merged_df["model"] == model]

    return merged_df