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

    # Normalize sales and inventory model names so they line up with the
    # master's canonical model name. Handles:
    #   - Case mismatches:  "AM-W33 pro"  → "AM-W33 Pro"
    #                       "AM-C11 PRO"  → "AM-C11 Pro"
    #                       "AM-C3A"      → "AM-C3a"
    #   - Variant suffixes after '-':  "ETC-07-WH"     → "ETC-07"
    #   - Bundle descriptors in parens: "UB-01 (AI-04…)" → "UB-01"
    master_models = set(master["Model"].astype(str).str.strip().unique())
    master_models_lower = {m.lower(): m for m in master_models}

    def normalize_model(m):
        m = str(m).strip()
        if not m:
            return m
        # Exact match
        if m in master_models:
            return m
        # Case-insensitive match — return the master's canonical casing
        if m.lower() in master_models_lower:
            return master_models_lower[m.lower()]
        # Try stripping after last '-' (variant suffix)
        parts = m.rsplit("-", 1)
        if len(parts) == 2:
            if parts[0] in master_models:
                return parts[0]
            if parts[0].lower() in master_models_lower:
                return master_models_lower[parts[0].lower()]
        # Try stripping after '(' (bundle suffix)
        base = m.split("(")[0].strip()
        if base in master_models:
            return base
        if base.lower() in master_models_lower:
            return master_models_lower[base.lower()]
        return m

    sales["model"]    = sales["model"].apply(normalize_model)
    inventory["Model"] = inventory["Model"].apply(normalize_model)

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

    # Channel filter:
    # - Audio Array → Amazon only (no 1p Sales)
    # - Nexlev / Viomi / White Mulberry → Amazon + 1p Sales (other channels excluded)
    if account.upper() == "AUDIO ARRAY":
        sales_n = sales_n[sales_n["channel"] == "Amazon"]
    elif account.upper() in ("NEXLEV", "VIOMI", "WHITE MULBERRY"):
        sales_n = sales_n[sales_n["channel"].isin(["Amazon", "1p Sales"])]

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
    # AMPM INVENTORY (SKU-keyed with safe Model fallback)
    # ---------------------------------------------
    # Primary: SKU-keyed lookup against AMPM-channel rows of the inventory
    # snapshot. SKU is the unambiguous physical-stock owner — it prevents
    # variants/Pro-vs-base SKUs from inheriting each other's AMPM pool.
    #
    # Fallback: when the SKU misses AND the master file has *exactly one*
    # row with that Model, fall back to summing AMPM by Model. This
    # catches cases where the warehouse labels the same physical product
    # under a different SKU than the operational master (e.g. master
    # carries the new ASIN's SKU "FBK80024" while the 440 units of
    # Model "SS-02" are sitting under the old SKU "FBA79589").
    #
    # The "Model unique in master" guard prevents the AI-02-style case
    # where two master SKUs legitimately share a Model and need separate
    # stock — fallback is skipped there so each SKU stays on its own
    # direct match (or 0 if it has no direct AMPM line).
    ampm_inv = inventory[
        inventory["Channel"].astype(str).str.strip().str.lower() == "ampm"
    ].copy()
    ampm_inv["_sku"]   = ampm_inv["SKU"].astype(str).str.strip().str.upper()
    ampm_inv["_model"] = ampm_inv["Model"].astype(str).str.strip().str.lower()
    ampm_qty_by_sku = (
        ampm_inv.groupby("_sku", as_index=False)["Qty"].sum()
                .set_index("_sku")["Qty"].to_dict()
    )

    # ORPHAN inventory rows = those whose SKU isn't in the operational master.
    # These are the rows where the warehouse labels the same physical product
    # under a different SKU than the master uses (e.g. master "FBK80024" vs
    # inventory "FBA79589" for Model SS-02). Only orphan rows feed the Model
    # fallback — preventing the AI-02 case where FBA79070's stock would
    # otherwise spill onto FBA76733.
    master_skus = set(master["SKU"].astype(str).str.strip().str.upper())
    ampm_orphan = ampm_inv[~ampm_inv["_sku"].isin(master_skus)]
    ampm_orphan_qty_by_model = (
        ampm_orphan.groupby("_model", as_index=False)["Qty"].sum()
                   .set_index("_model")["Qty"].to_dict()
    )

    master_model_count = (
        master["Model"].astype(str).str.strip().str.lower().value_counts().to_dict()
    )

    by_sku_col      = df["SKU"].astype(str).str.strip().str.upper().map(ampm_qty_by_sku).fillna(0)
    model_lower     = df["Model"].astype(str).str.strip().str.lower()
    by_model_orphan = model_lower.map(ampm_orphan_qty_by_model).fillna(0)
    master_cnt      = model_lower.map(master_model_count).fillna(0)

    # Fallback fires only when:
    #   - SKU-keyed lookup returned 0, AND
    #   - the master has exactly one row with this Model (no variant ambiguity), AND
    #   - the Model fallback pool is built only from orphan inventory rows
    #     (so we never re-allocate stock that's already owned by another SKU)
    fallback = (by_sku_col == 0) & (master_cnt == 1)
    df["ampm_inventory"] = by_sku_col.where(~fallback, by_model_orphan)

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