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
# SHIPMENTS (Nexlev + Viomi)
# ==========================================
print("Uploading shipments...")

ship_nexlev = pd.read_csv("data/input/fba_shipments_nexlev.csv")
ship_viomi = pd.read_csv("data/input/fba_shipments_viomi.csv")

# Clean column names
ship_nexlev.columns = ship_nexlev.columns.str.strip()
ship_viomi.columns = ship_viomi.columns.str.strip()

# Add account column (CRITICAL)
ship_nexlev["account"] = "nexlev"
ship_viomi["account"] = "viomi"

# Combine
shipments = pd.concat([ship_nexlev, ship_viomi], ignore_index=True)

# Normalize account column
shipments["account"] = shipments["account"].str.lower().str.strip()

# Upload
shipments.to_sql(
    "shipments",
    engine,
    if_exists="replace",
    index=False
)

print("✅ Shipments uploaded")
print(shipments["account"].value_counts())

# ==========================================
# INVENTORY LEDGER (Nexlev + Viomi)
# ==========================================
print("Uploading inventory ledger...")

ledger_nexlev = pd.read_csv("data/input/inventory_ledger_nexlev.csv")
ledger_viomi = pd.read_csv("data/input/inventory_ledger_viomi.csv")

ledger_nexlev.columns = ledger_nexlev.columns.str.strip()
ledger_viomi.columns = ledger_viomi.columns.str.strip()

ledger_nexlev["account"] = "nexlev"
ledger_viomi["account"] = "viomi"

ledger = pd.concat([ledger_nexlev, ledger_viomi], ignore_index=True)

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