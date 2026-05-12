import pandas as pd
from pathlib import Path
from typing import Tuple
from app.services.file_cache import get, get_excel_sheet

# =================================================
# CONFIG
# =================================================
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "input"


SALES_FILE = DATA_DIR / "weekly_sales_snapshot.csv"
AMAZON_INV_NEXLEV = DATA_DIR / "inventory_amazon_nexlev.csv"
AMAZON_INV_AUDIO_ARRAY = DATA_DIR / "inventory_amazon_audio_array.csv"
AMAZON_INV_WM = DATA_DIR / "inventory_amazon_WM.csv"

WAREHOUSE_INV_FILE = DATA_DIR / "inventory_snapshot_nexlev.xlsx"
WAREHOUSE_INV_AUDIO_ARRAY = DATA_DIR / "Inventory_snapshot_audio_array.xlsx"
WAREHOUSE_INV_WM = DATA_DIR / "Inventory_snapshot_WM.xlsx"

AMAZON_INV_VIOMI = DATA_DIR / "inventory_amazon_viomi.csv"

AA_WM_MASTER_FILE = DATA_DIR / "Audio Array & WM Replenishment" / "AA & WM Replenishment.xlsx"


# =================================================
# LOADERS
# =================================================
def load_data(account: str):

    if not SALES_FILE.exists():
        raise FileNotFoundError(f"Missing file: {SALES_FILE}")

    if not WAREHOUSE_INV_FILE.exists():
        raise FileNotFoundError(f"Missing file: {WAREHOUSE_INV_FILE}")

    if account.upper() == "NEXLEV":
        master = get("replenishment_master_nexlev.xlsx")

    elif account.upper() == "VIOMI":
        master = get("replenishment_master_viomi.xlsx")

    elif account.upper() == "AUDIO ARRAY":
        master = get_excel_sheet("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "AA")

    elif account.upper() == "WHITE MULBERRY":
        master = get_excel_sheet("Audio Array & WM Replenishment/AA & WM Replenishment.xlsx", "WM")

    else:
        raise ValueError(f"Unsupported account: {account}")

    sales = get("weekly_sales_snapshot.csv")

    if account.upper() == "NEXLEV":
        amazon_inventory = get("inventory_amazon_nexlev.csv")

    elif account.upper() == "VIOMI":
        amazon_inventory = get("inventory_amazon_viomi.csv")

    elif account.upper() == "AUDIO ARRAY":
        amazon_inventory = get("inventory_amazon_audio_array.csv")

    elif account.upper() == "WHITE MULBERRY":
        amazon_inventory = get("inventory_amazon_WM.csv")

    else:
        raise ValueError(f"Unsupported account: {account}")

    if account.upper() == "AUDIO ARRAY":
        inventory = get("Inventory_snapshot_audio_array.xlsx")

    elif account.upper() == "WHITE MULBERRY":
        inventory = get("Inventory_snapshot_WM.xlsx")

    else:
        inventory = get("inventory_snapshot_nexlev.xlsx")

    return master, sales, inventory, amazon_inventory


# =================================================
# SALES WINDOW HELPERS
# =================================================
def normalize_week_column(sales_df: pd.DataFrame) -> pd.DataFrame:
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
    df = df.sort_values("week_num", ascending=False)
    latest_weeks = df["week_num"].drop_duplicates().head(min(weeks, 12))
    return df[df["week_num"].isin(latest_weeks)]


# =================================================
# VALIDATION
# =================================================
def validate_columns(df: pd.DataFrame, required_cols: list, file_label: str):
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in {file_label}: {', '.join(missing)}")


# =================================================
# MASTER CARTON INTELLIGENCE
# =================================================
def compute_recommended_qty(replenishment_qty: int, master_carton: int, ixd_type: str) -> dict:
    """
    Computes the master-carton-rounded replenishment quantity.

    Rules:
    - Round to NEAREST carton, NOT always ceiling.
    - Tolerance: if remainder above floor boundary is ≤ 10% of carton size,
      round DOWN — 1 or 2 units adjustment is acceptable, no point sending
      a full extra carton.
    - Carton break flag: if rounding up adds > 50% of one carton in excess,
      flag it — breaking is smarter than over-sending.
    - IXD: full cartons mandatory.
    - Non-IXD: advisory, carton break always allowed.

    Examples:
      qty=41, carton=40 → remainder=1 (2.5% ≤ 10%) → round DOWN → 40, 1 carton
      qty=69, carton=40 → remainder=29 → round UP → 80, 2 cartons, excess=11
      qty=25, carton=40 → remainder=25 → round UP → 40, 1 carton, excess=15 (37%)
      qty=22, carton=40 → remainder=22 → round UP → 40, 1 carton, excess=18 (45%)
      qty=21, carton=40 → remainder=21 → round UP → 40, 1 carton, excess=19 (47%)
      qty=61, carton=40 → remainder=21 → round UP → 80, 2 cartons, excess=19 (47%)
    """
    if not master_carton or master_carton <= 0 or replenishment_qty <= 0:
        return {
            "recommended_qty": replenishment_qty,
            "carton_break_flag": False,
            "cartons_needed": 0,
            "excess_units": 0,
        }

    import math

    floor_cartons = replenishment_qty // master_carton
    ceil_cartons = math.ceil(replenishment_qty / master_carton)
    floor_qty = floor_cartons * master_carton
    ceil_qty = ceil_cartons * master_carton
    remainder = replenishment_qty - floor_qty

    # Tolerance: ≤ 10% of carton → round down, minor adjustment acceptable
    tolerance = master_carton * 0.10

    if remainder == 0:
        cartons_needed = floor_cartons
        final_qty = floor_qty
        excess_units = 0
        carton_break_flag = False
    elif remainder <= tolerance:
        # e.g. qty=41, carton=40 → round down to 40
        cartons_needed = floor_cartons
        final_qty = floor_qty
        excess_units = 0
        carton_break_flag = False
    else:
        # Round up
        cartons_needed = ceil_cartons
        final_qty = ceil_qty
        excess_units = ceil_qty - replenishment_qty
        carton_break_flag = excess_units > (master_carton * 0.5)

    return {
        "recommended_qty": int(final_qty),
        "carton_break_flag": bool(carton_break_flag),
        "cartons_needed": int(cartons_needed),
        "excess_units": int(excess_units),
    }


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
    amazon_inventory.columns = amazon_inventory.columns.str.strip()

    master["ASIN"] = master["ASIN"].astype(str).str.strip()
    amazon_inventory["asin"] = amazon_inventory["asin"].astype(str).str.strip()

    validate_columns(inventory, ["Model", "Channel", "Qty"], "inventory snapshot")
    validate_columns(sales, ["model", "units_sold", "week"], "sales snapshot")

    # Normalize sales model names — strip variant suffixes like "ETC-07-WH" → "ETC-07"
    # Check if master models are a prefix of sales models and normalize accordingly
    master_models = set(master["Model"].astype(str).str.strip().unique())
    def normalize_model(m):
        m = str(m).strip()
        # If exact match exists, keep as is
        if m in master_models:
            return m
        # Try stripping after last '-' if result matches master
        parts = m.rsplit("-", 1)
        if len(parts) == 2 and parts[0] in master_models:
            return parts[0]
        # Try stripping after '(' like "UB-01 (AI-04...)" → "UB-01"
        base = m.split("(")[0].strip()
        if base in master_models:
            return base
        return m
    sales["model"] = sales["model"].apply(normalize_model)

    # ---------------------------------------------
    # SALES WINDOW
    # ---------------------------------------------
    sales_n = get_last_n_weeks_sales(sales, sales_window)

    # Filter sales by brand to prevent cross-brand model collisions (e.g. PB-01 in Nexlev vs Audio Array)
    # Nexlev and Viomi share the same sales data (both tagged as "Nexlev" brand)
    # Audio Array and White Mulberry have their own brand tags
    if "brand" in sales_n.columns:
        if account.upper() in ("NEXLEV", "VIOMI"):
            # Exclude other brands — keep only Nexlev (shared by both accounts)
            sales_n = sales_n[sales_n["brand"].astype(str).str.strip() == "Nexlev"]
        elif account.upper() == "AUDIO ARRAY":
            sales_n = sales_n[sales_n["brand"].astype(str).str.strip() == "Audio Array"]
        elif account.upper() == "WHITE MULBERRY":
            sales_n = sales_n[sales_n["brand"].astype(str).str.strip() == "White Mulberry"]

    if account.upper() == "AUDIO ARRAY":
        sales_n = sales_n[sales_n["channel"] == "Amazon"]

    # ---------------------------------------------
    # AGGREGATE SALES
    # ---------------------------------------------
    velocity = (
        sales_n
        .groupby("model", as_index=False)
        .agg(total_units_sold=("units_sold", "sum"))
    )

    actual_weeks = sales_n["week"].nunique()

    velocity["sales_velocity"] = (
        velocity["total_units_sold"] / max(actual_weeks, 1)
    ).round(0)

    # ---------------------------------------------
    # MERGE WITH MASTER
    # ---------------------------------------------
    if "Status" in master.columns:
        master = master.rename(columns={"Status": "listing_status"})
    else:
        print("WARNING: 'Status' column NOT found in master. Available:", master.columns.tolist())
        master["listing_status"] = "-"

    df = master.merge(velocity, left_on="Model", right_on="model", how="left")

    df = df.merge(amazon_inventory, left_on="ASIN", right_on="asin", how="left")

    df["amazon_inventory"] = df["amazon_inventory"].fillna(0)
    df["inbound_inventory"] = df["inbound_inventory"].fillna(0)

    # ---------------------------------------------
    # NULL SAFETY
    # ---------------------------------------------
    df["sales_velocity"] = df["sales_velocity"].fillna(0)
    df["total_units_sold"] = df["total_units_sold"].fillna(0)

    # ---------------------------------------------
    # INVENTORY SUMMARY
    # ---------------------------------------------
    inventory_summary = (
        inventory
        .groupby(["Model", "Channel"])["Qty"]
        .sum()
        .unstack(fill_value=0)
        .reset_index()
    )

    inventory_summary["ampm_inventory"] = (
        inventory_summary["AMPM"].fillna(0)
        if "AMPM" in inventory_summary.columns
        else 0
    )

    df = df.merge(inventory_summary[["Model", "ampm_inventory"]], on="Model", how="left")

    df["amazon_inventory"] = df["amazon_inventory"].fillna(0)
    df["ampm_inventory"] = df["ampm_inventory"].fillna(0)

    # ---------------------------------------------
    # REQUIREMENT CALCULATION
    # ---------------------------------------------
    df["required_units"] = (df["sales_velocity"] * replenish_weeks).round(0)

    # ---------------------------------------------
    # FBA REPLENISHMENT (raw need = required - on-hand FBA)
    # ---------------------------------------------
    raw_replenishment = (
        df["required_units"] - df["amazon_inventory"]
    ).clip(lower=0)

    # ---------------------------------------------
    # WAREHOUSE SHORTFALL — computed BEFORE capping so we still
    # surface how much the mother warehouse is short of the full need.
    # ---------------------------------------------
    df["warehouse_shortfall"] = (
        raw_replenishment - df["ampm_inventory"]
    ).clip(lower=0)

    # ---------------------------------------------
    # CAP AT MOTHER WAREHOUSE (AMPM) STOCK
    # Can't ship more than the mother warehouse actually has.
    # ---------------------------------------------
    df["replenishment_qty"] = pd.concat(
        [raw_replenishment, df["ampm_inventory"]], axis=1
    ).min(axis=1)

    # ---------------------------------------------
    # FLAGS
    # ---------------------------------------------
    df["is_risky"] = df["amazon_inventory"] < df["sales_velocity"]
    df["is_overstock"] = df["amazon_inventory"] > (df["sales_velocity"] * 8)

    # ---------------------------------------------
    # MASTER CARTON INTELLIGENCE (NEW)
    # Compute IXD type first, then apply rounding logic
    # ---------------------------------------------
    def get_ixd_type(row):
        haz = str(row.get("Hazmat/non-Hazmat", "")).strip()
        return "Non-IXD" if haz == "Non-IXD Non Hazmat" else "IXD"

    df["_ixd_type"] = df.apply(get_ixd_type, axis=1)

    def apply_carton_intelligence(row):
        mc = row.get("Master Carton", 0)
        try:
            mc = int(mc)
        except (ValueError, TypeError):
            mc = 0
        result = compute_recommended_qty(
            replenishment_qty=int(row["replenishment_qty"]),
            master_carton=mc,
            ixd_type=row["_ixd_type"],
        )
        return pd.Series(result)

    carton_cols = df.apply(apply_carton_intelligence, axis=1)
    df["recommended_qty"] = carton_cols["recommended_qty"]
    df["carton_break_flag"] = carton_cols["carton_break_flag"]
    df["cartons_needed"] = carton_cols["cartons_needed"]
    df["excess_units"] = carton_cols["excess_units"]

    # Cap carton-rounded qty at mother warehouse stock too — if carton math
    # rounded up past what AMPM holds, ship only what AMPM has.
    df["recommended_qty"] = df[["recommended_qty", "ampm_inventory"]].min(axis=1).astype(int)

    # ---------------------------------------------
    # FINAL SHAPING FOR API
    # ---------------------------------------------
    df = df.drop(columns=["model", "_ixd_type"], errors="ignore")

    preferred_order = [
        "Model",
        "listing_status",
        "sales_velocity",
        "total_units_sold",
        "amazon_inventory",
        "inbound_inventory",
        "ampm_inventory",
        "required_units",
        "replenishment_qty",
        "warehouse_shortfall",
        "is_risky",
        "is_overstock",
        "Master Carton",
        "recommended_qty",
        "carton_break_flag",
        "cartons_needed",
        "excess_units",
    ]

    existing_cols = [c for c in preferred_order if c in df.columns]
    remaining_cols = [c for c in df.columns if c not in existing_cols]

    df = df[existing_cols + remaining_cols]
    df = df.rename(columns={"Model": "model"})

    return df