import pandas as pd
from pathlib import Path
from typing import Tuple

# =================================================
# CONFIG
# =================================================
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "input"


SALES_FILE = DATA_DIR / "weekly_sales_snapshot.csv"
AMAZON_INV_NEXLEV = DATA_DIR / "inventory_amazon_nexlev.csv"

WAREHOUSE_INV_FILE = DATA_DIR / "inventory_snapshot_nexlev.xlsx"
AMAZON_INV_VIOMI = DATA_DIR / "inventory_amazon_viomi.csv"


# =================================================
# LOADERS
# =================================================
def load_data(account: str):

    if not SALES_FILE.exists():
        raise FileNotFoundError(f"Missing file: {SALES_FILE}")

    if not WAREHOUSE_INV_FILE.exists():
        raise FileNotFoundError(f"Missing file: {WAREHOUSE_INV_FILE}")

    if account.upper() == "VIOMI":
        master_file = DATA_DIR / "replenishment_master_viomi.xlsx"
    else:
        master_file = DATA_DIR / "replenishment_master_nexlev.xlsx"

    if not master_file.exists():
        raise FileNotFoundError(f"Missing file: {master_file}")

    master = pd.read_excel(master_file)
    sales = pd.read_csv(SALES_FILE)
    
    if account.upper() == "VIOMI":
        amazon_inventory = pd.read_csv(AMAZON_INV_VIOMI)
    else:
        amazon_inventory = pd.read_csv(AMAZON_INV_NEXLEV)

    inventory = pd.read_excel(WAREHOUSE_INV_FILE)
    

    return master, sales, inventory, amazon_inventory


# =================================================
# SALES WINDOW HELPERS
# =================================================
def normalize_week_column(sales_df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalizes week column.
    Expected formats:
      - 'Week 4'
      - 'week 4'
      - '4'
    """

    df = sales_df.copy()

    df["week_num"] = (
        df["week"]
        .astype(str)
        .str.extract(r"(\d+)")
        .astype(float)
        .fillna(0)
        .astype(int)
    )

    return df


def get_last_n_weeks_sales(sales_df: pd.DataFrame, weeks: int) -> pd.DataFrame:

    df = normalize_week_column(sales_df)

    max_week = df["week_num"].max()

    # Always cap to 12 weeks
    window = min(weeks, 12)

    min_week = max(max_week - window + 1, 1)

    return df[(df["week_num"] >= min_week) & (df["week_num"] <= max_week)]


# =================================================
# VALIDATION
# =================================================
def validate_columns(df: pd.DataFrame, required_cols: list, file_label: str):
    """
    Ensure required columns exist.
    """

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing columns in {file_label}: {', '.join(missing)}"
        )


# =================================================
# MAIN BUSINESS LOGIC
# =================================================
def calculate_replenishment(
    sales_window: int,
    replenish_weeks: int,
    account: str = "NEXLEV"
) -> pd.DataFrame:
    """
    Core replenishment calculation.

    weeks:
      - number of weeks used from sales snapshot
      - SAME number of weeks used for coverage planning
    """

    # ---------------------------------------------
    # LOAD
    # ---------------------------------------------
    master, sales, inventory, amazon_inventory = load_data(account)

    amazon_inventory["amazon_inventory"] = (
    amazon_inventory["afn-total-quantity"]
    - amazon_inventory["afn-unsellable-quantity"]
)

    amazon_inventory["inbound_inventory"] = (
    amazon_inventory["afn-inbound-working-quantity"]
    + amazon_inventory["afn-inbound-shipped-quantity"]
)

    amazon_inventory = (
    amazon_inventory
    .groupby("asin", as_index=False)
    .agg(
        amazon_inventory=("amazon_inventory", "sum"),
        inbound_inventory=("inbound_inventory", "sum")
    )
)


    # ---------------------------------------------
    # NORMALIZE COLUMNS
    # ---------------------------------------------
    master.columns = master.columns.str.strip()
    sales.columns = sales.columns.str.strip()
    inventory.columns = inventory.columns.str.strip()

    validate_columns(
        inventory,
        ["Model", "Channel", "Qty"],
        "inventory snapshot"
        )


    validate_columns(
        sales,
        ["model", "units_sold", "week"],
        "sales snapshot"
    )

    # ---------------------------------------------
    # SALES WINDOW
    # ---------------------------------------------
    sales_n = get_last_n_weeks_sales(sales, sales_window)  

    # ---------------------------------------------
    # AGGREGATE SALES
    # ---------------------------------------------
    velocity = (
        sales_n
        .groupby("model", as_index=False)
        .agg(
            total_units_sold=("units_sold", "sum")
        )
    )

    # Average weekly velocity
    velocity["sales_velocity"] = (
    velocity["total_units_sold"] / max(sales_window, 1)
).round(0)

    # ---------------------------------------------
    # MERGE WITH MASTER
    # ---------------------------------------------
    df = master.merge(
        velocity,
        left_on="Model",
        right_on="model",
        how="left",
    )
    
    df = df.merge(
        amazon_inventory,
        left_on="ASIN",
        right_on="asin",
        how="left"
        )
    
    df["amazon_inventory"] = df["amazon_inventory"].fillna(0)

    # ---------------------------------------------
    # NULL SAFETY
    # ---------------------------------------------
    df["sales_velocity"] = df["sales_velocity"].fillna(0)
    df["total_units_sold"] = df["total_units_sold"].fillna(0)

    # ---------------------------------------------
    # UI-SAFE COLUMN ALIASES
    # (frontend depends on these exact keys)
    # ---------------------------------------------
    inventory_summary = (
    inventory
    .groupby(["Model", "Channel"])["Qty"]
    .sum()
    .unstack(fill_value=0)
    .reset_index()
)

    inventory_summary["ampm_inventory"] = inventory_summary.get("AMPM", 0)

    df = df.merge(
    inventory_summary[["Model","ampm_inventory"]],
    on="Model",
    how="left"
)

    df["amazon_inventory"] = df["amazon_inventory"].fillna(0)
    df["ampm_inventory"] = df["ampm_inventory"].fillna(0)
    # ---------------------------------------------
    # REQUIREMENT CALCULATION
    # ---------------------------------------------
    # Requirement = avg weekly velocity × coverage weeks
    df["required_units"] = (
    df["sales_velocity"] * replenish_weeks
).round(0)

    # ---------------------------------------------
    # FBA REPLENISHMENT
    # ---------------------------------------------
    # How much needs to be SENT to Amazon
    df["replenishment_qty"] = (
        df["required_units"] - df["amazon_inventory"]
    ).clip(lower=0)

    # ---------------------------------------------
    # WAREHOUSE SHORTFALL (REORDER SIGNAL)
    # ---------------------------------------------
    # If AMPM < required FBA replenishment
    df["warehouse_shortfall"] = (
        df["replenishment_qty"] - df["ampm_inventory"]
    ).clip(lower=0)

    # ---------------------------------------------
    # FLAGS FOR DASHBOARD
    # ---------------------------------------------
    # Risky = < 1 week cover
    df["is_risky"] = df["amazon_inventory"] < df["sales_velocity"]

    # Overstock = > 8 weeks cover
    df["is_overstock"] = df["amazon_inventory"] > (df["sales_velocity"] * 8)

    # ---------------------------------------------
    # FINAL SHAPING FOR API
    # ---------------------------------------------
    df = df.drop(columns=["model"], errors="ignore")

    # Explicit column order (optional but safer)
    preferred_order = [
        "Model",
        "sales_velocity",
        "total_units_sold",
        "amazon_inventory",
        "ampm_inventory",
        "required_units",
        "replenishment_qty",
        "warehouse_shortfall",
        "is_risky",
        "is_overstock",
    ]

    existing_cols = [c for c in preferred_order if c in df.columns]
    remaining_cols = [c for c in df.columns if c not in existing_cols]

    df = df[existing_cols + remaining_cols]
    df = df.rename(columns={"Model": "model"})

    # ---------------------------------------------
    # DEBUG AID (safe to keep)
    # ---------------------------------------------
    # Uncomment if needed
    # print(df.columns.tolist())

    return df