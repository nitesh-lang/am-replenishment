import pandas as pd
from pathlib import Path

DATA_PATH = Path("data/input/Fossil Replenishment")

def load_fossil_replenishment(replenish_weeks=8):

    # FILES
    master_file = DATA_PATH / "Fossil Replenishment.xlsx"
    cambium_file = DATA_PATH / "Cambium - SOH.xlsx"
    sales_file = DATA_PATH / "fba_shipments_fossil.csv"

    # LOAD DATA
    master_df = pd.read_excel(master_file)
    cambium_df = pd.read_excel(cambium_file)
    sales_df = pd.read_csv(sales_file)

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
    # REQUIRED INVENTORY
    # =====================

    master_df["Required Inventory"] = master_df["Fossil Weekly Sales"] * replenish_weeks

    # =====================
    # REPLENISHMENT QTY
    # =====================

    master_df["Replenishment Qty"] = (
        master_df["Required Inventory"] - master_df["Total Inventory"]
    ).clip(lower=0)

    master_df = master_df.fillna(0)

    return master_df