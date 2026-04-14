import pandas as pd
from pathlib import Path
from app.services.file_cache import get

DATA_PATH = Path("data/input/Fossil Replenishment")

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
    amazon_df     = get("inventory_amazon_fossil.xlsx")
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
    # AMAZON INVENTORY LOOKUP (ledger)
    # Source: inventory_amazon_fossil.xlsx
    # Key: SKU → Qty, filtered by Channel=Amazon
    # =====================

    amazon_df.columns = amazon_df.columns.str.strip()
    amazon_filtered = amazon_df[
        amazon_df["Channel"].str.strip().str.lower() == "amazon"
    ]
    amazon_map = amazon_filtered.groupby("SKU")["Qty"].sum()
    master_df["Amazon Inventory"] = master_df["SKU"].map(amazon_map).fillna(0)

    # =====================
    # OTHER STOCK (from Fossil Replenishment.xlsx)
    # =====================

    for col in ["Andheri/Goregaon sellable Stock", "Open PO"]:
        if col in master_df.columns:
            master_df[col] = pd.to_numeric(master_df[col], errors="coerce").fillna(0)
        else:
            master_df[col] = 0

    # =====================
    # IN TRANSIT — read from In-Transit_Open_PO_Fossil.xlsx
    # Sum Packing List Qty per Item No where PO fulfillment Remark = In-Transit
    # =====================
    try:
        po_df = get("Fossil Replenishment/In-Transit_Open_PO_Fossil.xlsx")
        po_df.columns = po_df.columns.str.strip()
        po_df["Item No"] = po_df["Item No"].astype(str).str.strip().str.upper()
        po_df["packing_list_qty"] = pd.to_numeric(po_df["Packing List Qty"], errors="coerce").fillna(0)
        in_transit_df = (
            po_df[po_df["PO fulfillment Remark"].astype(str).str.strip() == "In-Transit"]
            .groupby("Item No", as_index=False)
            .agg(in_transit_total=("packing_list_qty", "sum"))
        )
        master_df["_item_no_upper"] = master_df["Item No"].astype(str).str.strip().str.upper()
        master_df = master_df.merge(in_transit_df, left_on="_item_no_upper", right_on="Item No", how="left", suffixes=("", "_it"))
        master_df["In Transit PO"] = master_df["in_transit_total"].fillna(0).astype(int)
        master_df.drop(columns=["_item_no_upper", "in_transit_total", "Item No_it"], inplace=True, errors="ignore")
    except Exception as e:
        print(f"⚠️ Fossil Replenishment In-Transit load error: {e}")
        master_df["In Transit PO"] = pd.to_numeric(master_df.get("In Transit PO", 0), errors="coerce").fillna(0)

    # =====================
    # TOTAL INVENTORY
    # =====================

    for col in ["Cambium SOH", "Amazon Inventory", "Andheri/Goregaon sellable Stock", "In Transit PO", "Open PO"]:
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
        "FBA79633", "FBA79527", "FBA79882"
    }
    master_df.loc[master_df["SKU"].isin(CORE_SKUS), "Weeks of Cover"] = 12

    # =====================
    # REQUIRED INVENTORY
    # =====================

    master_df["Required Inventory"] = (
        master_df["Fossil Weekly Sales"] * master_df["Weeks of Cover"]
    )

    # =====================
    # REPLENISHMENT QTY
    # =====================

    master_df["Replenishment Qty"] = (
        master_df["Required Inventory"] - master_df["Total Inventory"]
    ).clip(lower=0)

    # If Fossil SOH is 0, no requirement — Fossil doesn't hold the stock
    master_df.loc[master_df["Fossil SOH"] == 0, "Replenishment Qty"] = 0

    # Preserve string columns before blanket fillna(0)
    str_cols = ["SKU", "ASIN", "Item No", "Brand", "Assortment Type", "Fossil Assortment", "Category"]
    for col in str_cols:
        if col in master_df.columns:
            master_df[col] = master_df[col].fillna("").astype(str).str.strip()

    master_df = master_df.fillna(0)

    return master_df, available_weeks