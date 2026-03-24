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
    #  brand (lowercase)       : { assortment_type : weeks }
    "fossil"          : {"FP": 9, "Discount": 4, "VD": 6},
    "armani exchange" : {"FP": 6, "Discount": 4, "VD": 6},
    "michael kors"    : {"FP": 6, "Discount": 4, "VD": 6},
    "emporio armani"  : {"FP": 4, "Discount": 4, "VD": 6},
    "diesel"          : {"FP": 4, "Discount": 4, "VD": 6},
    "skagen"          : {"FP": 4, "Discount": 4, "VD": 6},
}

DEFAULT_WEEKS = 8  # fallback for unknown brand/type


def get_weeks_of_cover(brand: str, assortment_type: str) -> int:
    """
    Return weeks of cover for a given brand + assortment type.
    - brand: e.g. 'Fossil', 'Armani Exchange' (case-insensitive)
    - assortment_type: 'FP', 'Discount', or 'VD'
    """
    b = str(brand).strip().lower()
    a = str(assortment_type).strip()

    # Normalise common variants
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


def load_fossil_replenishment():

    # LOAD DATA
    master_df = get("Fossil Replenishment/Fossil Replenishment.xlsx")
    cambium_df = get("Fossil Replenishment/Cambium - SOH.xlsx")
    sales_df   = get("Fossil Replenishment/fba_shipments_fossil.csv")

    # =====================
    # CAMBIUM SOH LOOKUP
    # =====================

    cambium_map = cambium_df.set_index("Item No")["Available Qty"]
    master_df["Cambium SOH"] = master_df["Item No"].map(cambium_map).fillna(0)

    # =====================
    # OTHER STOCK (TEMP)
    # =====================

    master_df["Andheri/Goregaon sellable Stock"] = 0
    master_df["In Transit PO"] = 0
    master_df["Open PO"] = 0

    # =====================
    # TOTAL INVENTORY
    # =====================

    master_df["Total Inventory"] = (
        master_df["Cambium SOH"]
        + master_df["Andheri/Goregaon sellable Stock"]
        + master_df["In Transit PO"]
        + master_df["Open PO"]
    )

    # =====================
    # SALES
    # =====================

    sales_df.columns = sales_df.columns.str.strip()

    sales_df["Merchant SKU"] = sales_df["Merchant SKU"].str.replace(
        r"^(FBK|FBO|FBA)", "FBA", regex=True
    )

    sales_3m = (
        sales_df.groupby("Merchant SKU")["Shipped Quantity"]
        .sum()
        .reset_index()
    )

    master_df = master_df.merge(
        sales_3m.rename(columns={"Merchant SKU": "SKU"}),
        on="SKU",
        how="left"
    )

    master_df["3 Months Gross Sales"] = master_df["Shipped Quantity"].fillna(0)

    # =====================
    # WEEKLY SALES
    # =====================

    master_df["Fossil Weekly Sales"] = master_df["3 Months Gross Sales"] / 12

    # =====================
    # WEEKS OF COVER (per row)
    # Driven by Brand x Assortment Type matrix
    # =====================

    master_df["Weeks of Cover"] = master_df.apply(
        lambda row: get_weeks_of_cover(
            row.get("Brand", ""),
            row.get("Assortment Type", "FP")
        ),
        axis=1
    )

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

    master_df = master_df.fillna(0)

    return master_df