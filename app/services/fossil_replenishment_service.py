import pandas as pd
from pathlib import Path
from app.services.file_cache import get

DATA_PATH = Path("data/input/Fossil Replenishment")

# =============================================
# STOCKOUT RECOVERY DETECTION
# =============================================
# SKUs that hit Fossil SOH = 0 for >= this many past weeks in the
# fossil_soh_history.csv AND currently have SOH > 0 get auto-promoted to
# 12-week cover with a Remarks note. Rationale: their reported weekly
# sales are stockout-suppressed, so the matrix-based cover would under-
# order. Detected dynamically from history — no manual maintenance.
STOCKOUT_ZERO_WEEK_THRESHOLD = 3


def _detect_stockout_recovery() -> dict[str, dict]:
    """Return per-SKU dict of stockout-recovery signals from history CSV.

    Only returns SKUs meeting:
      - >= STOCKOUT_ZERO_WEEK_THRESHOLD zero-SOH weeks in past snapshots
      - Current SOH (latest snapshot) > 0 (supply is back)

    Value dict: {zero_weeks, peak_soh, current_soh}
    """
    hist_path = DATA_PATH / "fossil_soh_history.csv"
    if not hist_path.exists():
        return {}
    try:
        h = pd.read_csv(hist_path)
    except Exception:
        return {}
    if h.empty or "SKU" not in h.columns or "Fossil SOH" not in h.columns:
        return {}
    h["Fossil SOH"] = pd.to_numeric(h["Fossil SOH"], errors="coerce").fillna(0).astype(int)
    latest_date = h["snapshot_date"].max()
    current = h[h["snapshot_date"] == latest_date].set_index("SKU")["Fossil SOH"]
    past = h[h["snapshot_date"] != latest_date]
    zero_wks = past.groupby("SKU")["Fossil SOH"].apply(lambda s: int((s == 0).sum()))
    peak = h.groupby("SKU")["Fossil SOH"].max()

    out: dict[str, dict] = {}
    for sku, zw in zero_wks.items():
        if zw < STOCKOUT_ZERO_WEEK_THRESHOLD:
            continue
        cs = int(current.get(sku, 0))
        if cs <= 0:
            continue
        out[sku] = {
            "zero_weeks":  int(zw),
            "peak_soh":    int(peak.get(sku, 0)),
            "current_soh": cs,
        }
    return out

# =============================================
# WEEKS OF COVER MATRIX
# Brand x Assortment Type (FP / Discount / VD)
# =============================================
#
#                   Discount   Full Price   VD
#   Fossil             4           9         6
#   Armani Exchange    4           6         6
#   Michael Kors       4           6         6
#   Emporio Armani     4           4         6
#   Diesel             4           4         6
#   Skagen             4           4         6

WEEKS_OF_COVER_MATRIX = {
    "fossil"          : {"FP": 9, "Discount": 4, "VD": 6},
    "armani exchange" : {"FP": 6, "Discount": 4, "VD": 6},
    "michael kors"    : {"FP": 6, "Discount": 4, "VD": 6},
    "emporio armani"  : {"FP": 4, "Discount": 4, "VD": 6},
    "diesel"          : {"FP": 4, "Discount": 4, "VD": 6},
    "skagen"          : {"FP": 4, "Discount": 4, "VD": 6},
}

DEFAULT_WEEKS = 8


def get_weeks_of_cover(brand: str, assortment_type: str) -> int:
    b = str(brand).strip().lower()
    a = str(assortment_type).strip()

    a_upper = a.upper()
    if a_upper in ("FULL PRICE", "FP"):
        a = "FP"
    elif a_upper in ("DISCOUNT", "DISCOUNTED"):
        a = "Discount"
    elif a_upper == "VD":
        a = "VD"

    brand_row = WEEKS_OF_COVER_MATRIX.get(b)
    if brand_row:
        return brand_row.get(a, DEFAULT_WEEKS)

    return DEFAULT_WEEKS


def load_fossil_replenishment(from_week: int = None, to_week: int = None, cover_weeks: int = None):

    # =====================
    # LOAD DATA
    # =====================

    master_df     = get("Fossil Replenishment/Fossil Replenishment.xlsx")
    master_df.columns = master_df.columns.str.strip()
    sales_df      = get("weekly_sales_snapshot.csv")

    # =====================
    # FOSSIL SOH LOOKUP (inhouse / AMPM)
    # Source: Fossil - SOH.xlsx
    # Key: Item No → Available Qty
    # =====================

    # Fossil SOH comes directly from master file (column already present)
    if "Fossil SOH" not in master_df.columns:
        master_df["Fossil SOH"] = 0
    master_df["Fossil SOH"] = pd.to_numeric(master_df["Fossil SOH"], errors="coerce").fillna(0)

    # =====================
    # OTHER STOCK (from Fossil Replenishment.xlsx)
    # =====================

    for col in ["Andheri/Goregaon sellable Stock", "In Transit PO", "Open PO"]:
        if col in master_df.columns:
            master_df[col] = pd.to_numeric(master_df[col], errors="coerce").fillna(0)
        else:
            master_df[col] = 0

    # =====================
    # TOTAL INVENTORY
    # =====================

    for col in ["Cambium SOH", "Andheri/Goregaon sellable Stock", "In Transit PO", "Open PO"]:
        master_df[col] = pd.to_numeric(master_df[col], errors="coerce").fillna(0)

    master_df["Total Inventory"] = (
        master_df["Cambium SOH"]
        + master_df["Andheri/Goregaon sellable Stock"]
        + master_df["In Transit PO"]
        + master_df["Open PO"]
    )

    # =====================
    # SALES — weekly_sales_snapshot.csv
    # Filter: brand=Fossil, channel=Amazon
    # =====================

    sales_df.columns = sales_df.columns.str.strip()
    sales_df["brand"]   = sales_df["brand"].str.strip()
    sales_df["channel"] = sales_df["channel"].str.strip().str.lower()

    fossil_sales = sales_df[
        (sales_df["brand"].str.lower() == "fossil") &
        (sales_df["channel"] == "amazon")
    ].copy()

    # =====================
    # AVAILABLE WEEKS
    # Parse "Week 13" → 13
    # =====================

    fossil_sales["week_num"] = (
        fossil_sales["week"].str.extract(r"(\d+)").astype(float)
    )
    available_weeks = sorted(
        fossil_sales["week_num"].dropna().unique().astype(int).tolist()
    )

    # =====================
    # FILTER BY SALES WINDOW
    # =====================

    filtered_sales = fossil_sales.copy()
    if from_week:
        filtered_sales = filtered_sales[filtered_sales["week_num"] >= from_week]
    if to_week:
        filtered_sales = filtered_sales[filtered_sales["week_num"] <= to_week]

    # =====================
    # CALCULATE WEEK COUNT FOR AVG
    # =====================

    if available_weeks:
        eff_from   = from_week if from_week else available_weeks[0]
        eff_to     = to_week   if to_week   else available_weeks[-1]
        week_count = max(len([w for w in available_weeks if eff_from <= w <= eff_to]), 1)
    else:
        week_count = 12

    # =====================
    # AGGREGATE SALES BY SKU
    # =====================

    sales_agg = (
        filtered_sales.groupby("sku")["units_sold"]
        .sum()
        .reset_index()
    )

    master_df = master_df.merge(
        sales_agg.rename(columns={"sku": "SKU", "units_sold": "units_sold_window"}),
        on="SKU",
        how="left"
    )

    master_df["3 Months Gross Sales"] = master_df["units_sold_window"].fillna(0)

    # =====================
    # WEEKLY SALES
    # =====================

    master_df["Fossil Weekly Sales"] = master_df["3 Months Gross Sales"] / week_count

    # =====================
    # LAST 4 WEEKS AVG (independent of selected window)
    # Used to bump Required Inventory for FP/Discount when
    # recent demand outpaces the 12-week average.
    # =====================

    last_4_weeks = sorted(available_weeks)[-4:] if available_weeks else []
    last_4_count = max(len(last_4_weeks), 1)
    last_4_sales = fossil_sales[fossil_sales["week_num"].isin(last_4_weeks)]
    last_4_agg = (
        last_4_sales.groupby("sku")["units_sold"]
        .sum()
        .reset_index()
        .rename(columns={"sku": "SKU", "units_sold": "_last_4_sum"})
    )
    master_df = master_df.merge(last_4_agg, on="SKU", how="left")
    master_df["_last_4_sum"] = master_df["_last_4_sum"].fillna(0)
    master_df["Last 4 Weeks Top Avg"] = master_df["_last_4_sum"] / last_4_count
    master_df = master_df.drop(columns=["_last_4_sum"])

    # =====================
    # WEEKS OF COVER (per row)
    # Driven by Brand x Assortment Type matrix
    # Unless cover_weeks override is passed
    # =====================

    master_df["Weeks of Cover"] = master_df.apply(
        lambda row: get_weeks_of_cover(
            row.get("Brand", ""),
            row.get("Assortment Type", "FP")
        ),
        axis=1
    )

    if cover_weeks:
        master_df["Weeks of Cover"] = cover_weeks

    # Core ASINs — ALWAYS 12 weeks, overrides matrix AND manual selection
    CORE_SKUS = {
        "FBA66963", "FBA66636", "FBA69595",
        "FBA79633", "FBA79527", "FBA79882",
        "FBA79627",  # AX4184 — Armani Exchange FP
        "FBA79528",  # ES5362 — Fossil FP
        "FBA79929",  # ES5439 — Fossil FP
    }
    master_df.loc[master_df["SKU"].isin(CORE_SKUS), "Weeks of Cover"] = 12

    # Stockout-recovery auto-promotion — SKUs that hit SOH=0 in prior
    # weeks (their reported sales are suppressed) but supply is back now
    # get boosted to 12-week cover. Detected dynamically from
    # fossil_soh_history.csv. Also captures the "old cover" so the
    # Remarks column can explain the elevation for the operator.
    stockout_signals = _detect_stockout_recovery()
    master_df["_prev_cover"] = master_df["Weeks of Cover"].astype(int)
    if stockout_signals:
        so_skus = list(stockout_signals.keys())
        master_df.loc[master_df["SKU"].isin(so_skus), "Weeks of Cover"] = 12

    # =====================
    # REQUIRED INVENTORY
    # For FP/Discount, use the higher of 12-week avg vs last-4-week avg so
    # recent demand spikes flow through into the reorder.
    # =====================

    def _effective_weekly_sales(row):
        a = str(row.get("Assortment Type", "")).strip().upper()
        if a in ("FP", "FULL PRICE", "DISCOUNT", "DISCOUNTED"):
            return max(row["Fossil Weekly Sales"], row["Last 4 Weeks Top Avg"])
        return row["Fossil Weekly Sales"]

    effective_sales = master_df.apply(_effective_weekly_sales, axis=1)
    master_df["Required Inventory"] = effective_sales * master_df["Weeks of Cover"]

    # =====================
    # REPLENISHMENT QTY
    # =====================

    master_df["Replenishment Qty"] = (
        master_df["Required Inventory"] - master_df["Total Inventory"]
    ).clip(lower=0)

    # If Fossil SOH is 0, no requirement — Fossil doesn't hold the stock
    master_df.loc[master_df["Fossil SOH"] == 0, "Replenishment Qty"] = 0

    # Cap at Fossil SOH — can't send more than what Fossil actually has
    master_df["Replenishment Qty"] = master_df[["Replenishment Qty", "Fossil SOH"]].min(axis=1)

    # =====================
    # REMARKS (stockout recovery elevation)
    # For any SKU auto-promoted via stockout-recovery, show operator:
    #   how many zero-SOH weeks were detected, peak SOH seen, cover
    #   boosted from Xwk to 12wk, and the additional Required Inventory
    #   that boost added over the matrix cover.
    # =====================
    master_df["Remarks"] = ""
    if stockout_signals:
        eff_now = effective_sales  # already computed above
        for sku, sig in stockout_signals.items():
            mask = master_df["SKU"] == sku
            if not mask.any():
                continue
            idx = master_df.index[mask][0]
            prev_cov = int(master_df.at[idx, "_prev_cover"])
            if prev_cov >= 12:
                continue  # already at 12wk via CORE_SKUS — no elevation to report
            eff = float(eff_now.iloc[idx] if hasattr(eff_now, 'iloc') else eff_now[idx])
            uplift = int(round(eff * (12 - prev_cov)))
            master_df.at[idx, "Remarks"] = (
                f"Stockout recovery: {sig['zero_weeks']}wk zero-SOH history "
                f"(peak SOH {sig['peak_soh']}, current {sig['current_soh']}); "
                f"cover boosted {prev_cov}→12wk (+{uplift} units)"
            )

    master_df = master_df.drop(columns=["_prev_cover"], errors="ignore")

    # Preserve string columns before blanket fillna(0)
    str_cols = ["SKU", "ASIN", "Item No", "Brand", "Assortment Type", "Fossil Assortment", "Category", "Remarks"]
    for col in str_cols:
        if col in master_df.columns:
            master_df[col] = master_df[col].fillna("").astype(str).str.strip()

    master_df = master_df.fillna(0)

    return master_df, available_weeks