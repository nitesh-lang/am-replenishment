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
    # AGGREGATE SALES — ASIN primary, SKU fallback, Model fallback
    # ---------------------------------------------
    # ASIN-keyed attribution avoids the duplicate-Model double-count when
    # a master has multiple SKUs sharing one Model (AA: 12 such pairs;
    # Nexlev/Viomi: 1 pair on SW-01). Each cascade level is EXCLUSIVE —
    # contains only sales rows that couldn't be attributed by a higher
    # priority key. Guarantees every sales row counts exactly once.
    sales_n = sales_n.copy()
    sales_n["_asin"] = sales_n.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    sales_n["_sku"]  = sales_n.get("sku", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})

    velocity_by_asin = (
        sales_n[sales_n["_asin"] != ""]
        .groupby("_asin", as_index=False)
        .agg(total_units_sold_asin=("units_sold", "sum"))
    )
    velocity_by_sku = (
        sales_n[(sales_n["_asin"] == "") & (sales_n["_sku"] != "")]
        .groupby("_sku", as_index=False)
        .agg(total_units_sold_sku=("units_sold", "sum"))
    )
    velocity_by_model = (
        sales_n[(sales_n["_asin"] == "") & (sales_n["_sku"] == "")]
        .groupby("model", as_index=False)
        .agg(total_units_sold_model=("units_sold", "sum"))
    )

    actual_weeks = max(sales_n["week"].nunique(), 1)

    # ---------------------------------------------
    # MERGE WITH MASTER
    # ---------------------------------------------
    if "Status" in master.columns:
        master = master.rename(columns={"Status": "listing_status"})
    else:
        print("WARNING: 'Status' column NOT found in master. Available:", master.columns.tolist())
        master["listing_status"] = "-"

    df = master.copy()
    df["_asin"] = df["ASIN"].astype(str).str.strip().str.upper()
    df["_sku"]  = df["SKU"].astype(str).str.strip().str.upper() if "SKU" in df.columns else ""

    df = df.merge(velocity_by_asin,  left_on="_asin", right_on="_asin", how="left")
    df = df.merge(velocity_by_sku,   left_on="_sku",  right_on="_sku",  how="left")
    df = df.merge(velocity_by_model, left_on="Model", right_on="model", how="left")
    df["total_units_sold"] = (
        df["total_units_sold_asin"]
        .fillna(df["total_units_sold_sku"])
        .fillna(df["total_units_sold_model"])
        .fillna(0)
    )
    df["sales_velocity"] = (df["total_units_sold"] / actual_weeks).round(0)
    df = df.drop(columns=[c for c in [
        "total_units_sold_asin", "total_units_sold_sku", "total_units_sold_model",
        "_asin", "_sku",
    ] if c in df.columns])

    # ---------------------------------------------
    # LAST 4 WEEKS VELOCITY BUMP (all accounts)
    # Velocity = max(window-avg, last-4-ISO-week avg) so recent demand
    # spikes flow through to required_units / replenishment_qty. Last 4
    # weeks = the 4 most recent ISO weeks in the loaded sales data,
    # independent of the user's From/To selector.
    # ---------------------------------------------
    df["window_velocity"]    = df["sales_velocity"]
    df["window_units_sold"]  = df["total_units_sold"]

    sales_4 = get_last_n_weeks_sales(sales, 4)
    if "brand" in sales_4.columns:
        if account.upper() in ("NEXLEV", "VIOMI"):
            sales_4 = sales_4[sales_4["brand"].astype(str).str.strip() == "Nexlev"]
        elif account.upper() == "AUDIO ARRAY":
            sales_4 = sales_4[sales_4["brand"].astype(str).str.strip() == "Audio Array"]
        elif account.upper() == "WHITE MULBERRY":
            sales_4 = sales_4[sales_4["brand"].astype(str).str.strip() == "White Mulberry"]
    if account.upper() == "AUDIO ARRAY":
        sales_4 = sales_4[sales_4["channel"] == "Amazon"]
    elif account.upper() in ("NEXLEV", "VIOMI", "WHITE MULBERRY"):
        sales_4 = sales_4[sales_4["channel"].isin(["Amazon", "1p Sales"])]

    sales_4 = sales_4.copy()
    sales_4["_asin"] = sales_4.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    sales_4["_sku"]  = sales_4.get("sku",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})

    v4_asin = (
        sales_4[sales_4["_asin"] != ""]
        .groupby("_asin", as_index=False)
        .agg(units_4w_asin=("units_sold", "sum"))
    )
    v4_sku = (
        sales_4[(sales_4["_asin"] == "") & (sales_4["_sku"] != "")]
        .groupby("_sku", as_index=False)
        .agg(units_4w_sku=("units_sold", "sum"))
    )
    v4_model = (
        sales_4[(sales_4["_asin"] == "") & (sales_4["_sku"] == "")]
        .groupby("model", as_index=False)
        .agg(units_4w_model=("units_sold", "sum"))
        .rename(columns={"model": "_model_key"})
    )

    actual_weeks_4 = max(sales_4["week"].nunique(), 1) if len(sales_4) else 1

    df["_asin"] = df["ASIN"].astype(str).str.strip().str.upper()
    df["_sku"]  = df["SKU"].astype(str).str.strip().str.upper() if "SKU" in df.columns else ""

    df = df.merge(v4_asin,  on="_asin", how="left")
    df = df.merge(v4_sku,   on="_sku",  how="left")
    df = df.merge(v4_model, left_on="Model", right_on="_model_key", how="left")

    for c in ("units_4w_asin", "units_4w_sku", "units_4w_model"):
        if c not in df.columns:
            df[c] = 0

    df["units_last_4w"] = (
        df["units_4w_asin"]
        .fillna(df["units_4w_sku"])
        .fillna(df["units_4w_model"])
        .fillna(0)
    )
    df["last_4_velocity"] = (df["units_last_4w"] / actual_weeks_4).round(0)

    df["sales_velocity"] = df[["window_velocity", "last_4_velocity"]].max(axis=1)
    df["velocity_basis"] = "window"
    df.loc[df["last_4_velocity"] > df["window_velocity"], "velocity_basis"] = "4wk"

    df = df.drop(columns=[c for c in [
        "units_4w_asin", "units_4w_sku", "units_4w_model",
        "_asin", "_sku", "_model_key",
    ] if c in df.columns])

    df = df.merge(amazon_inventory, left_on="ASIN", right_on="asin", how="left")

    df["amazon_inventory"] = df["amazon_inventory"].fillna(0)
    df["inbound_inventory"] = df["inbound_inventory"].fillna(0)

    # ---------------------------------------------
    # NULL SAFETY
    # ---------------------------------------------
    df["sales_velocity"]    = df["sales_velocity"].fillna(0)
    df["window_velocity"]   = df["window_velocity"].fillna(0)
    df["last_4_velocity"]   = df["last_4_velocity"].fillna(0)
    df["total_units_sold"]  = df["total_units_sold"].fillna(0)
    df["units_last_4w"]     = df["units_last_4w"].fillna(0)

    # ---------------------------------------------
    # AMPM INVENTORY — ASIN primary, SKU fallback, Model fallback (exclusive)
    # ---------------------------------------------
    # Cascade matches the project standard set in CB / WM / china_reorder.
    # ASIN-primary anchors on the most stable identity and avoids silent
    # zeros when the inventory snapshot's Model string drifts from the
    # master's Model (e.g. "POS BRACKET" in snapshot vs "POSS-01" in master).
    # Each level is exclusive — every AMPM file row counts exactly once.
    ampm_inv = inventory[
        inventory["Channel"].astype(str).str.strip().str.lower() == "ampm"
    ].copy()
    ampm_inv["_asin"]  = ampm_inv.get("ASIN", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    ampm_inv["_sku"]   = ampm_inv.get("SKU",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    ampm_inv["_model"] = ampm_inv["Model"].astype(str).str.strip().str.lower()

    # ASIN: rows w/ non-empty ASIN, grouped by ASIN.
    # SKU: rows w/ non-empty SKU, grouped by SKU (non-exclusive — catches the
    #       ASIN-drift case where master.ASIN != file.ASIN but SKU matches).
    # Model: rows w/ EMPTY ASIN AND SKU only (exclusive — prevents duplicate-
    #       Model master rows from double-counting the shared pool).
    ampm_by_asin = (
        ampm_inv[ampm_inv["_asin"] != ""]
        .groupby("_asin", as_index=False)["Qty"].sum()
        .set_index("_asin")["Qty"].to_dict()
    )
    ampm_by_sku = (
        ampm_inv[ampm_inv["_sku"] != ""]
        .groupby("_sku", as_index=False)["Qty"].sum()
        .set_index("_sku")["Qty"].to_dict()
    )
    ampm_by_model = (
        ampm_inv[(ampm_inv["_asin"] == "") & (ampm_inv["_sku"] == "")]
        .groupby("_model", as_index=False)["Qty"].sum()
        .set_index("_model")["Qty"].to_dict()
    )

    _master_asin = df["ASIN"].astype(str).str.strip().str.upper()
    _master_sku  = df["SKU"].astype(str).str.strip().str.upper() if "SKU" in df.columns else pd.Series([""] * len(df))
    _master_mod  = df["Model"].astype(str).str.strip().str.lower()

    df["ampm_inventory"] = [
        ampm_by_asin.get(a, ampm_by_sku.get(s, ampm_by_model.get(m, 0)))
        for a, s, m in zip(_master_asin, _master_sku, _master_mod)
    ]

    df["amazon_inventory"] = df["amazon_inventory"].fillna(0)
    df["ampm_inventory"] = pd.to_numeric(df["ampm_inventory"], errors="coerce").fillna(0)

    # ---------------------------------------------
    # B2B INVENTORY (display only — does not feed required_units / replen)
    # Same ASIN→SKU→Model exclusive cascade as AMPM, filtered to
    # Channel == "B2B - AMPM" in the inventory snapshot.
    # ---------------------------------------------
    b2b_inv = inventory[
        inventory["Channel"].astype(str).str.strip().str.lower() == "b2b - ampm"
    ].copy()
    b2b_inv["_asin"]  = b2b_inv.get("ASIN", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    b2b_inv["_sku"]   = b2b_inv.get("SKU",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    b2b_inv["_model"] = b2b_inv["Model"].astype(str).str.strip().str.lower()

    b2b_by_asin = (
        b2b_inv[b2b_inv["_asin"] != ""]
        .groupby("_asin", as_index=False)["Qty"].sum()
        .set_index("_asin")["Qty"].to_dict()
    )
    b2b_by_sku = (
        b2b_inv[b2b_inv["_sku"] != ""]
        .groupby("_sku", as_index=False)["Qty"].sum()
        .set_index("_sku")["Qty"].to_dict()
    )
    b2b_by_model = (
        b2b_inv[(b2b_inv["_asin"] == "") & (b2b_inv["_sku"] == "")]
        .groupby("_model", as_index=False)["Qty"].sum()
        .set_index("_model")["Qty"].to_dict()
    )

    df["b2b_inventory"] = [
        b2b_by_asin.get(a, b2b_by_sku.get(s, b2b_by_model.get(m, 0)))
        for a, s, m in zip(_master_asin, _master_sku, _master_mod)
    ]
    df["b2b_inventory"] = pd.to_numeric(df["b2b_inventory"], errors="coerce").fillna(0)

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
    # WEEKLY SALES ARRAY (for sparklines + detail-row 12-wk chart)
    # ASIN → SKU → Model cascade, same as velocity. Returns one int per
    # ISO week in chronological order matching `weekly_window`.
    # ---------------------------------------------
    sales_for_spark = sales_n.copy()
    sales_for_spark["_asin"] = sales_for_spark.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    sales_for_spark["_sku"]  = sales_for_spark.get("sku",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})

    if "week_num" not in sales_for_spark.columns:
        sales_for_spark = normalize_week_column(sales_for_spark)

    weeks_sorted = sorted(int(w) for w in sales_for_spark["week_num"].dropna().unique())
    n_weeks = max(len(weeks_sorted), 1)

    def _weekly_dict(key_col, frame):
        if frame.empty:
            return {}
        piv = (
            frame.pivot_table(index=key_col, columns="week_num", values="units_sold", aggfunc="sum")
            .reindex(columns=weeks_sorted, fill_value=0)
            .fillna(0)
            .astype(int)
        )
        return {k: row.tolist() for k, row in piv.iterrows()}

    wk_by_asin  = _weekly_dict("_asin",  sales_for_spark[sales_for_spark["_asin"] != ""])
    wk_by_sku   = _weekly_dict("_sku",   sales_for_spark[(sales_for_spark["_asin"] == "") & (sales_for_spark["_sku"] != "")])
    wk_by_model = _weekly_dict("model",  sales_for_spark[(sales_for_spark["_asin"] == "") & (sales_for_spark["_sku"] == "")])

    _asin_keys = df["ASIN"].astype(str).str.strip().str.upper() if "ASIN" in df.columns else pd.Series([""] * len(df))
    _sku_keys  = df["SKU"].astype(str).str.strip().str.upper() if "SKU" in df.columns else pd.Series([""] * len(df))
    _mod_keys  = df["Model"].astype(str).str.strip() if "Model" in df.columns else pd.Series([""] * len(df))

    blank = [0] * n_weeks
    df["weekly_sales"] = [
        wk_by_asin.get(a) or wk_by_sku.get(s) or wk_by_model.get(m) or list(blank)
        for a, s, m in zip(_asin_keys, _sku_keys, _mod_keys)
    ]
    df["weekly_window"] = [list(weeks_sorted)] * len(df)

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