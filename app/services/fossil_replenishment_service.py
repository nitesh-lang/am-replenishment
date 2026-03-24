import pandas as pd
from pathlib import Path
from app.services.file_cache import get

DATA_PATH = Path("data/input/Fossil Replenishment")

# =====================
# WEEKS OF COVER MATRIX
# =====================
#
# Assortment Type: FP (Full Price), Discount, VD
#
# FP:
#   Fossil          → 9 weeks
#   AX / MK         → 6 weeks
#   EA / DZ / Skagen → 4 weeks
#
# Discount:
#   Fossil          → 4 weeks
#   AX / MK         → 4 weeks
#   EA / DZ / Skagen → 4 weeks
#
# VD (all brands)   → 6 weeks

FOSSIL_BRANDS    = {"fossil"}
AX_MK_BRANDS     = {"armani exchange", "michael kors"}
EA_DZ_SKG_BRANDS = {"emporio armani", "diesel", "skagen"}

def get_weeks_of_cover(brand: str, assortment_type: str) -> int:
    """
    Return the correct weeks-of-cover for a given brand + assortment type.
    Brand matching is case-insensitive.
    Assortment type: 'FP', 'Discount', or 'VD'
    """
    b = str(brand).strip().lower()
    a = str(assortment_type).strip().upper()

    # VD overrides brand
    if a == "VD":
        return 6

    if a == "FP":
        if b in FOSSIL_BRANDS:
            return 9
        if b in AX_MK_BRANDS:
            return 6
        if b in EA_DZ_SKG_BRANDS:
            return 4
        return 8  # fallback for unknown brands

    if a == "DISCOUNT":
        # All brands → 4 weeks for Discount
        return 4

    # Fallback for any unrecognised assortment type
    return 8


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
    # WEEKS OF COVER (per row, brand + assortment type aware)
    # =====================

    # Master file must have columns: "Brand" and "Assortment Type"
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