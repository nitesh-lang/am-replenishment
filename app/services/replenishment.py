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

    # Which SP-API inventory files to union for each account. Most accounts
    # have their SKUs listed only in their own Seller Central. WM SKUs are
    # ALSO listed in the Viomi seller account (operator confirmed
    # 2026-07-10: Viomi's SP-API pull returns 756 FBA units of WM ASINs
    # that WM's own file shows as 0), so WM must union both files.
    amazon_inv_map = {
        "NEXLEV":         ["inventory_amazon_nexlev.csv"],
        "VIOMI":          ["inventory_amazon_viomi.csv"],
        "AUDIO ARRAY":    ["inventory_amazon_audio_array.csv"],
        "WHITE MULBERRY": ["inventory_amazon_WM.csv", "inventory_amazon_viomi.csv"],
    }
    if account.upper() not in amazon_inv_map:
        raise ValueError(f"Unsupported account: {account}")
    _parts = [get(f) for f in amazon_inv_map[account.upper()]]
    amazon_inventory = pd.concat(_parts, ignore_index=True) if len(_parts) > 1 else _parts[0]

    if account.upper() == "AUDIO ARRAY":
        inventory = get("Inventory_snapshot_audio_array.xlsx")

    elif account.upper() == "WHITE MULBERRY":
        inventory = get("Inventory_snapshot_WM.xlsx")

    else:
        inventory = get("inventory_snapshot_nexlev.xlsx")

    # Ledger — used to compute Real AM Inventory
    # (Ending Warehouse Balance + In Transit Between Warehouses per SKU).
    # Captures Amazon-side warehouse-to-warehouse transfers that the
    # snapshot / afn-warehouse-quantity view misses.
    # WM ledger unions WM + Viomi for the same reason as amazon_inventory
    # above — some WM SKUs' ledger rows sit in the Viomi Seller Central
    # account rather than WM's own token.
    ledger_map = {
        "NEXLEV":         ["inventory_ledger_nexlev.csv"],
        "VIOMI":          ["inventory_ledger_viomi.csv"],
        "AUDIO ARRAY":    ["inventory_ledger_Audio Array.csv"],
        "WHITE MULBERRY": ["inventory_ledger_WM.csv", "inventory_ledger_viomi.csv"],
    }
    try:
        _lparts = [get(f) for f in ledger_map[account.upper()]]
        ledger = pd.concat(_lparts, ignore_index=True) if len(_lparts) > 1 else _lparts[0]
    except Exception:
        ledger = None

    return master, sales, inventory, amazon_inventory, ledger


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
def _apply_wm_channel_filter(sales_df: pd.DataFrame, master_df: pd.DataFrame) -> pd.DataFrame:
    """WM channel rule (2026-07-20): Monitor Arm SKUs use Amazon sales only;
    all other WM SKUs use Amazon + 1p Sales. Operator's Monitor Arm 1P
    orders are unreliable signal for replenishment planning.

    Identifies Monitor Arm rows via ASIN/SKU/Model set built from the WM
    master's Category column.
    """
    ma_asins: set[str] = set()
    ma_skus:  set[str] = set()
    ma_models: set[str] = set()
    if master_df is not None and "Category" in master_df.columns:
        mask = master_df["Category"].astype(str).str.strip().str.lower() == "monitor arm"
        if "ASIN" in master_df.columns:
            ma_asins = {a for a in master_df.loc[mask, "ASIN"].astype(str).str.strip().str.upper()
                        if a and a not in ("NAN", "NONE")}
        if "SKU" in master_df.columns:
            ma_skus = {s for s in master_df.loc[mask, "SKU"].astype(str).str.strip().str.upper()
                       if s and s not in ("NAN", "NONE")}
        if "Model" in master_df.columns:
            ma_models = {m for m in master_df.loc[mask, "Model"].astype(str).str.strip()
                         if m and m.lower() not in ("nan", "none")}

    a = sales_df.get("asin", pd.Series([""] * len(sales_df))).astype(str).str.strip().str.upper()
    s = sales_df.get("sku",  pd.Series([""] * len(sales_df))).astype(str).str.strip().str.upper()
    mo = sales_df.get("model", pd.Series([""] * len(sales_df))).astype(str).str.strip()

    is_monitor_arm = a.isin(ma_asins) | s.isin(ma_skus) | mo.isin(ma_models)
    ch = sales_df["channel"]

    # Monitor Arm → Amazon only; other WM → Amazon + 1p Sales
    keep = (ch == "Amazon") | ((ch == "1p Sales") & ~is_monitor_arm)
    return sales_df[keep]


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
    master, sales, inventory, amazon_inventory, ledger = load_data(account)


    # FBA Inv = units physically at Amazon FCs (excludes unsellable + inbound)
    #        = fulfillable + reserved (or equivalently, warehouse - unsellable)
    amazon_inventory["fba_inv"] = (
        amazon_inventory["afn-warehouse-quantity"]
        - amazon_inventory["afn-unsellable-quantity"]
    )

    # Inbound = every unit not yet counted in warehouse-quantity
    #        = working (plan created, not shipped) + shipped (in-transit)
    #          + receiving (arrived at FC, being checked in)
    amazon_inventory["inbound_inventory"] = (
        amazon_inventory["afn-inbound-working-quantity"]
        + amazon_inventory["afn-inbound-shipped-quantity"]
        + amazon_inventory["afn-inbound-receiving-quantity"]
    )

    # amazon_inventory (kept as-is for downstream math + labelled "Final Inv"
    # in UI) = FBA Inv + Inbound = afn-total - afn-unsellable
    amazon_inventory["amazon_inventory"] = (
        amazon_inventory["afn-total-quantity"]
        - amazon_inventory["afn-unsellable-quantity"]
    )

    amazon_inventory = (
        amazon_inventory
        .groupby("asin", as_index=False)
        .agg(
            amazon_inventory=("amazon_inventory", "sum"),
            fba_inv=("fba_inv", "sum"),
            inbound_inventory=("inbound_inventory", "sum"),
            afn_reserved=("afn-reserved-quantity", "sum"),
        )
    )

    # ---------------------------------------------
    # REAL AM INVENTORY — from ledger, SELLABLE disposition only
    # Amazon's FBA Ledger identity:
    #   Ending Balance = Starting + Receipts + Customer Returns
    #                  - Customer Shipments - Vendor Returns
    #                  + Found - Lost - Damaged - Disposed
    #                  + Warehouse Transfer In/Out + Other Events
    # So Ending Warehouse Balance already reflects every flow.
    # Real AM Inv = Ending Balance (at FC now)
    #             + In Transit Between Warehouses (mid-transfer, not in Ending)
    # Filter Disposition == "SELLABLE" — exclude damaged / carrier-damaged
    # / customer-damaged rows.
    # ---------------------------------------------
    if ledger is not None and len(ledger) > 0:
        led = ledger.copy()
        led.columns = led.columns.str.strip()
        led = led[led["Disposition"].astype(str).str.strip().str.upper() == "SELLABLE"].copy()
        # Filter to the latest date only — SP-API pull returns multi-day
        # history, we only want the freshest snapshot per SKU/FC.
        if "Date" in led.columns:
            led["_date_ord"] = pd.to_datetime(led["Date"], errors="coerce",
                                              format="%m/%d/%Y")
            # Fallback for dd-mm-yyyy from legacy manual drops
            mask_missing = led["_date_ord"].isna()
            if mask_missing.any():
                led.loc[mask_missing, "_date_ord"] = pd.to_datetime(
                    led.loc[mask_missing, "Date"], errors="coerce",
                    format="%d-%m-%Y"
                )
            latest_date = led["_date_ord"].max()
            if pd.notna(latest_date):
                led = led[led["_date_ord"] == latest_date].copy()
        led["_sku"] = led["MSKU"].astype(str).str.strip().str.upper()
        for c in ("Ending Warehouse Balance", "In Transit Between Warehouses"):
            if c in led.columns:
                led[c] = pd.to_numeric(led[c], errors="coerce").fillna(0)
            else:
                led[c] = 0
        real_am = (
            led.groupby("_sku", as_index=False)
               .agg(ledger_at_fc=("Ending Warehouse Balance", "sum"),
                    ledger_in_transit=("In Transit Between Warehouses", "sum"))
        )
        real_am["real_am_inv"] = (real_am["ledger_at_fc"] + real_am["ledger_in_transit"]).astype(int)
        real_am["ledger_at_fc"] = real_am["ledger_at_fc"].astype(int)
        real_am["ledger_in_transit"] = real_am["ledger_in_transit"].astype(int)
    else:
        real_am = pd.DataFrame(columns=["_sku", "ledger_at_fc", "ledger_in_transit", "real_am_inv"])

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
            # Tonor rows added to the AA master (2026-07-28) share the same
            # Amazon Seller account, so their weekly_sales_snapshot brand is
            # "Tonor". Include both so Tonor SKUs get proper velocity.
            sales_n = sales_n[sales_n["brand"].astype(str).str.strip().isin(["Audio Array", "Tonor"])]
        elif account.upper() == "WHITE MULBERRY":
            sales_n = sales_n[sales_n["brand"].astype(str).str.strip() == "White Mulberry"]

    # Channel filter:
    # - Audio Array → Amazon only (no 1p Sales)
    # - Nexlev / Viomi → Amazon + 1p Sales
    # - White Mulberry → Amazon + 1p Sales EXCEPT Monitor Arm SKUs (Amazon only)
    if account.upper() == "AUDIO ARRAY":
        sales_n = sales_n[sales_n["channel"] == "Amazon"]
    elif account.upper() in ("NEXLEV", "VIOMI"):
        sales_n = sales_n[sales_n["channel"].isin(["Amazon", "1p Sales"])]
    elif account.upper() == "WHITE MULBERRY":
        sales_n = _apply_wm_channel_filter(sales_n, master)

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
            sales_4 = sales_4[sales_4["brand"].astype(str).str.strip().isin(["Audio Array", "Tonor"])]
        elif account.upper() == "WHITE MULBERRY":
            sales_4 = sales_4[sales_4["brand"].astype(str).str.strip() == "White Mulberry"]
    if account.upper() == "AUDIO ARRAY":
        sales_4 = sales_4[sales_4["channel"] == "Amazon"]
    elif account.upper() in ("NEXLEV", "VIOMI"):
        sales_4 = sales_4[sales_4["channel"].isin(["Amazon", "1p Sales"])]
    elif account.upper() == "WHITE MULBERRY":
        sales_4 = _apply_wm_channel_filter(sales_4, master)

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

    # ---------------------------------------------
    # LAST-2-WEEK RECENCY BUMP (Fossil-style)
    # sales_velocity = max(selected window, last 4-week avg, last 2-week avg)
    # last-2 catches sharp recent trends that a wider window smooths out.
    # ---------------------------------------------
    sales_2 = get_last_n_weeks_sales(sales, 2)
    if "brand" in sales_2.columns:
        if account.upper() in ("NEXLEV", "VIOMI"):
            sales_2 = sales_2[sales_2["brand"].astype(str).str.strip() == "Nexlev"]
        elif account.upper() == "AUDIO ARRAY":
            sales_2 = sales_2[sales_2["brand"].astype(str).str.strip().isin(["Audio Array", "Tonor"])]
        elif account.upper() == "WHITE MULBERRY":
            sales_2 = sales_2[sales_2["brand"].astype(str).str.strip() == "White Mulberry"]
    if account.upper() == "AUDIO ARRAY":
        sales_2 = sales_2[sales_2["channel"] == "Amazon"]
    elif account.upper() in ("NEXLEV", "VIOMI"):
        sales_2 = sales_2[sales_2["channel"].isin(["Amazon", "1p Sales"])]
    elif account.upper() == "WHITE MULBERRY":
        sales_2 = _apply_wm_channel_filter(sales_2, master)

    sales_2 = sales_2.copy()
    sales_2["_asin"] = sales_2.get("asin", "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})
    sales_2["_sku"]  = sales_2.get("sku",  "").astype(str).str.strip().str.upper().replace({"NAN": "", "NONE": ""})

    v2_asin = (
        sales_2[sales_2["_asin"] != ""]
        .groupby("_asin", as_index=False)
        .agg(units_2w_asin=("units_sold", "sum"))
    )
    v2_sku = (
        sales_2[(sales_2["_asin"] == "") & (sales_2["_sku"] != "")]
        .groupby("_sku", as_index=False)
        .agg(units_2w_sku=("units_sold", "sum"))
    )
    v2_model = (
        sales_2[(sales_2["_asin"] == "") & (sales_2["_sku"] == "")]
        .groupby("model", as_index=False)
        .agg(units_2w_model=("units_sold", "sum"))
        .rename(columns={"model": "_model_key_2"})
    )
    actual_weeks_2 = max(sales_2["week"].nunique(), 1) if len(sales_2) else 1

    df["_asin"] = df["ASIN"].astype(str).str.strip().str.upper()
    df["_sku"]  = df["SKU"].astype(str).str.strip().str.upper() if "SKU" in df.columns else ""

    df = df.merge(v2_asin,  on="_asin", how="left")
    df = df.merge(v2_sku,   on="_sku",  how="left")
    df = df.merge(v2_model, left_on="Model", right_on="_model_key_2", how="left")

    for c in ("units_2w_asin", "units_2w_sku", "units_2w_model"):
        if c not in df.columns:
            df[c] = 0

    df["units_last_2w"] = (
        df["units_2w_asin"]
        .fillna(df["units_2w_sku"])
        .fillna(df["units_2w_model"])
        .fillna(0)
    )
    df["last_2_velocity"] = (df["units_last_2w"] / actual_weeks_2).round(0)

    # Effective velocity = max(selected window, last-2-week avg).
    # last_4_velocity is still computed above for display but is NOT part
    # of the sales_velocity max — operator wants a strict 2-signal check.
    df["sales_velocity"] = df[["window_velocity", "last_2_velocity"]].max(axis=1)
    df["velocity_basis"] = "window"
    df.loc[df["last_2_velocity"] > df["window_velocity"], "velocity_basis"] = "2wk"

    df = df.drop(columns=[c for c in [
        "units_4w_asin", "units_4w_sku", "units_4w_model",
        "units_2w_asin", "units_2w_sku", "units_2w_model",
        "_asin", "_sku", "_model_key", "_model_key_2",
    ] if c in df.columns])

    df = df.merge(amazon_inventory, left_on="ASIN", right_on="asin", how="left")

    df["amazon_inventory"] = df["amazon_inventory"].fillna(0)
    df["fba_inv"] = df["fba_inv"].fillna(0)
    df["inbound_inventory"] = df["inbound_inventory"].fillna(0)
    df["afn_reserved"] = df["afn_reserved"].fillna(0)

    # Real AM Inv from ledger — join on SKU (MSKU)
    df["_sku_key"] = df["SKU"].astype(str).str.strip().str.upper()
    df = df.merge(real_am, left_on="_sku_key", right_on="_sku", how="left")
    df["ledger_at_fc"] = df["ledger_at_fc"].fillna(0).astype(int)
    df["ledger_in_transit"] = df["ledger_in_transit"].fillna(0).astype(int)
    df["real_am_inv"] = df["real_am_inv"].fillna(0).astype(int)
    df = df.drop(columns=[c for c in ("_sku_key", "_sku") if c in df.columns])

    # Real AM Inv (available) = Real AM Inv − afn-reserved (clamped ≥ 0).
    # Reserved units are allocated to open customer orders (about to ship),
    # so they don't count as available for future demand.
    df["real_am_inv_available"] = (
        df["real_am_inv"] - df["afn_reserved"]
    ).clip(lower=0).astype(int)

    # Prefer Real AM Inv (ledger, reserve-adjusted) as the offset when
    # the ledger has data. Falls back to amazon_inventory (afn-total −
    # unsellable) when the ledger is empty (e.g., puller was skipped or
    # SP-API creds missing for this account).
    #
    # Fold Inbound into effective inventory — inbound units are planned
    # shipments already created (today / yesterday) and will land inside
    # the replenish window, so they should net down the ask instead of
    # forcing a duplicate top-up. The fallback path uses amazon_inventory
    # which already equals FBA + Inbound (afn-total − unsellable), so
    # only the ledger branch needs the explicit + inbound_inventory.
    if df["real_am_inv"].sum() > 0:
        df["effective_amazon_inv"] = (
            df["real_am_inv_available"] + df["inbound_inventory"]
        )
    else:
        df["effective_amazon_inv"] = df["amazon_inventory"]

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
    # FBA REPLENISHMENT (raw need = required - effective Amazon inventory)
    # effective_amazon_inv = Real AM Inv (available) + Inbound  (ledger path)
    #                     or amazon_inventory (Final Inv = FBA + Inbound)
    # ---------------------------------------------
    raw_replenishment = (
        df["required_units"] - df["effective_amazon_inv"]
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
    # AMPM BUFFER GATE — if mother warehouse stock is 1..10 units,
    # don't ship any of it. Keep it as a safety buffer for ad-hoc
    # pulls. Full raw need cascades to warehouse_shortfall (China
    # order picks up the 10 units we would have shipped).
    # AMPM = 0 is EXCLUDED: nothing to keep, and replenishment_qty
    # is already 0 via the min-cap above, so tagging it as buffer
    # would be misleading.
    # ---------------------------------------------
    AMPM_BUFFER_THRESHOLD = 10
    _ampm = pd.to_numeric(df["ampm_inventory"], errors="coerce").fillna(0)
    _low_ampm = (_ampm > 0) & (_ampm <= AMPM_BUFFER_THRESHOLD)
    df["buffer_note"] = ""
    df.loc[_low_ampm, "replenishment_qty"] = 0
    df.loc[_low_ampm, "warehouse_shortfall"] = raw_replenishment[_low_ampm]
    df.loc[_low_ampm, "buffer_note"] = "kept for buffer"

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
        # Nexlev/Viomi master: "Hazmat/non-Hazmat" column with values like
        # "Non-IXD Non Hazmat" vs blank/other.
        # AA/WM master: only "Hazmat Type" column with values "IXD" / "NON IXD".
        # Check both, treat any variant that says "NON IXD" or "Non-IXD" as
        # non-IXD; everything else defaults to IXD.
        haz = str(row.get("Hazmat/non-Hazmat", "")).strip()
        if haz == "Non-IXD Non Hazmat":
            return "Non-IXD"
        typ = str(row.get("Hazmat Type", "")).strip().upper()
        if typ in ("NON IXD", "NON-IXD", "NONIXD"):
            return "Non-IXD"
        return "IXD"

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
        "fba_inv",
        "inbound_inventory",
        "amazon_inventory",
        "real_am_inv",
        "ledger_at_fc",
        "ledger_in_transit",
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

    # ---------------------------------------------
    # AMPM OOS momentum signals (last 13 weeks / 3 months)
    # Enriches every row with three fields based on git-log-reconstructed
    # AMPM history. Non-blocking — if history read fails, defaults to 0/blank.
    # ---------------------------------------------
    try:
        from app.services.ampm_history import compute_oos_signals
        brand_map = {
            "NEXLEV":         "Nexlev",
            "VIOMI":          "Viomi",
            "AUDIO ARRAY":    "Audio Array",
            "WHITE MULBERRY": "White Mulberry",
        }
        brand_name = brand_map.get(account.upper(), account)
        _sku_norm = df["SKU"].astype(str).str.strip().str.upper() if "SKU" in df.columns \
                    else df.get("sku", pd.Series("", index=df.index)).astype(str).str.strip().str.upper()
        _cur_ampm = pd.Series(
            pd.to_numeric(df["ampm_inventory"], errors="coerce").fillna(0).values,
            index=_sku_norm.values,
        )
        signals = compute_oos_signals(brand_name, sales, weeks=13,
                                      current_ampm_series=_cur_ampm,
                                      master_df=master)
        if not signals.empty:
            df["_sku_norm"] = _sku_norm.values
            df = df.merge(
                signals.reset_index(),
                left_on="_sku_norm", right_on="sku",
                how="left", suffixes=("", "_y"),
            )
            df = df.drop(columns=[c for c in ("_sku_norm", "sku_y") if c in df.columns])
        df["oos_weeks_3m"]   = pd.to_numeric(df.get("oos_weeks_3m", 0),   errors="coerce").fillna(0).astype(int)
        df["thin_weeks_3m"]  = pd.to_numeric(df.get("thin_weeks_3m", 0),  errors="coerce").fillna(0).astype(int)
        df["lost_units_3m"]  = pd.to_numeric(df.get("lost_units_3m", 0),  errors="coerce").fillna(0).astype(int)
        df["momentum_flag"]  = df.get("momentum_flag", pd.Series("", index=df.index)).fillna("").astype(str)
    except Exception as e:
        print(f"⚠️ AMPM momentum enrichment skipped: {e}")
        df["oos_weeks_3m"]  = 0
        df["thin_weeks_3m"] = 0
        df["lost_units_3m"] = 0
        df["momentum_flag"] = ""

    return df