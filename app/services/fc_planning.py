from app.services.validation_engine import run_full_validation
from app.services.file_cache import get, get_excel_sheet
import os
import re
import pandas as pd
from pathlib import Path


# =================================================
# FILE MAP — account → ledger + FBA Sales filename aliases
# =================================================
# Shipments now come from per-week files under data/input/FBA Sales/Week N/.
# Each brand may have multiple acceptable filename stems (case-insensitive).
# Ledger stays on its existing per-brand consolidated file.

ACCOUNT_FILES = {
    "nexlev": {
        "fba_aliases": ["nex", "nexlev"],
        "ledger":      "inventory_ledger_nexlev.csv",
    },
    "viomi": {
        "fba_aliases": ["vibc", "viomi"],
        "ledger":      "inventory_ledger_viomi.csv",
    },
    "white mulberry": {
        "fba_aliases": ["crpl"],
        "ledger":      "inventory_ledger_WM.csv",
    },
    "audio array": {
        "fba_aliases": ["audio array"],
        "ledger":      "inventory_ledger_Audio Array.csv",
    },
    "fossil": {
        "fba_aliases": ["cr", "cambium retail"],
        "ledger":      "Fossil Replenishment/inventory_ledger_fossil.csv",
    },
}


# Repo-relative path to the per-week FBA Sales folder
_FBA_SALES_ROOT = Path(__file__).resolve().parent.parent.parent / "data" / "input" / "FBA Sales"


def list_available_fba_weeks() -> list[int]:
    """Return sorted ISO-week numbers present under data/input/FBA Sales/.

    e.g., [12, 13, 14, ..., 23]. Used by the API so the UI Range picker
    can populate the From/To dropdowns with actual week numbers.
    """
    if not _FBA_SALES_ROOT.exists():
        return []
    week_pat = re.compile(r"^Week\s+(\d+)$", re.IGNORECASE)
    weeks = []
    for p in _FBA_SALES_ROOT.iterdir():
        if p.is_dir():
            m = week_pat.match(p.name)
            if m:
                weeks.append(int(m.group(1)))
    return sorted(weeks)


def count_available_fba_weeks() -> int:
    """Legacy helper — keep for backward compat."""
    return len(list_available_fba_weeks())


def _load_weekly_fba_shipments(
    brand_aliases: list[str],
    sales_window: int = 12,
    from_week: int | None = None,
    to_week:   int | None = None,
) -> pd.DataFrame:
    """Concatenate per-week FBA Sales CSVs for a brand.

    Selection priority:
      1. If BOTH from_week AND to_week are provided → use that inclusive
         ISO-week range (e.g. from=12, to=20 includes 12,13,...,20).
      2. Else → fall back to "last N weeks" via sales_window.

    Returns empty DataFrame if no matching files. Weeks in the requested
    range that don't have folders are silently skipped.
    """
    if not _FBA_SALES_ROOT.exists():
        return pd.DataFrame()
    aliases = {a.strip().lower() for a in brand_aliases}
    week_pat = re.compile(r"^Week\s+(\d+)$", re.IGNORECASE)

    week_folders = []
    for wf in _FBA_SALES_ROOT.iterdir():
        if not wf.is_dir():
            continue
        m = week_pat.match(wf.name)
        if not m:
            continue
        week_folders.append((int(m.group(1)), wf))

    if not week_folders:
        return pd.DataFrame()

    if from_week is not None and to_week is not None:
        lo, hi = sorted([int(from_week), int(to_week)])
        selected = [(w, p) for (w, p) in week_folders if lo <= w <= hi]
    else:
        # last N weeks (desc by week number)
        week_folders.sort(key=lambda x: x[0], reverse=True)
        window = max(int(sales_window), 1)
        selected = week_folders[:window]

    frames: list[pd.DataFrame] = []
    for _, wf in selected:
        for csv in wf.glob("*.csv"):
            if csv.stem.strip().lower() in aliases:
                try:
                    frames.append(pd.read_csv(csv))
                except Exception as e:
                    print(f"⚠️ Failed to read {csv}: {e}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# =================================================
# DATA LOADERS — reads directly from repo files
# =================================================
def load_fc_data(
    account: str,
    sales_window: int = 12,
    from_week: int | None = None,
    to_week:   int | None = None,
):
    key = account.strip().lower()
    if key not in ACCOUNT_FILES:
        raise ValueError(f"Unknown account for FC data: {account}")

    files = ACCOUNT_FILES[key]
    shipments = _load_weekly_fba_shipments(
        files["fba_aliases"],
        sales_window=sales_window,
        from_week=from_week,
        to_week=to_week,
    )
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
    account: str,
    sales_window: int = 12,
    from_week: int | None = None,
    to_week:   int | None = None,
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

    shipments, ledger = load_fc_data(
        account,
        sales_window=sales_window,
        from_week=from_week,
        to_week=to_week,
    )

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