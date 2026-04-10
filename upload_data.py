import pandas as pd
from sqlalchemy import create_engine
import os

# ==========================================
# DATABASE CONNECTION (Use ENV if available)
# ==========================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://am_replenishment_db_user:4M8xsThJDkrNgaL0siQaGN0kbx9ZPqhR@dpg-d6e55uv5r7bs73belrm0-a.virginia-postgres.render.com/am_replenishment_db"
)

engine = create_engine(DATABASE_URL)

# ==========================================
# SHIPMENTS (all accounts)
# ==========================================
print("Uploading shipments...")

ship_nexlev = pd.read_csv("data/input/fba_shipments_nexlev.csv")
ship_viomi  = pd.read_csv("data/input/fba_shipments_viomi.csv")
ship_wm     = pd.read_csv("data/input/fba_shipments_WM.csv")
ship_aa     = pd.read_csv("data/input/fba_shipments_Audio Array.csv")
ship_fossil = pd.read_csv("data/input/Fossil Replenishment/fba_shipments_fossil.csv")

for df in [ship_nexlev, ship_viomi, ship_wm, ship_aa, ship_fossil]:
    df.columns = df.columns.str.strip()

ship_nexlev["account"] = "nexlev"
ship_viomi["account"]  = "viomi"
ship_wm["account"]     = "white mulberry"
ship_aa["account"]     = "audio array"
ship_fossil["account"] = "fossil"

shipments = pd.concat(
    [ship_nexlev, ship_viomi, ship_wm, ship_aa, ship_fossil],
    ignore_index=True
)

shipments["account"] = shipments["account"].str.lower().str.strip()

shipments.to_sql(
    "shipments",
    engine,
    if_exists="replace",
    index=False
)

print("✅ Shipments uploaded")
print(shipments["account"].value_counts())

# ==========================================
# INVENTORY LEDGER (all accounts)
# ==========================================
print("Uploading inventory ledger...")

ledger_nexlev = pd.read_csv("data/input/inventory_ledger_nexlev.csv")
ledger_viomi  = pd.read_csv("data/input/inventory_ledger_viomi.csv")
ledger_wm     = pd.read_csv("data/input/inventory_ledger_WM.csv")
ledger_aa     = pd.read_csv("data/input/inventory_ledger_Audio Array.csv")
ledger_fossil = pd.read_csv("data/input/Fossil Replenishment/inventory_ledger_fossil.csv")

for df in [ledger_nexlev, ledger_viomi, ledger_wm, ledger_aa, ledger_fossil]:
    df.columns = df.columns.str.strip()

ledger_nexlev["account"] = "nexlev"
ledger_viomi["account"]  = "viomi"
ledger_wm["account"]     = "white mulberry"
ledger_aa["account"]     = "audio array"
ledger_fossil["account"] = "fossil"

ledger = pd.concat(
    [ledger_nexlev, ledger_viomi, ledger_wm, ledger_aa, ledger_fossil],
    ignore_index=True
)

ledger["account"] = ledger["account"].str.lower().str.strip()

ledger.to_sql(
    "inventory_ledger",
    engine,
    if_exists="replace",
    index=False
)

print("✅ Inventory ledger uploaded")
print(ledger["account"].value_counts())

print("🚀 All data uploaded successfully")