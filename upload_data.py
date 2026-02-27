import pandas as pd
from sqlalchemy import create_engine

# 🔴 Use your EXTERNAL database URL
engine = create_engine(
    "postgresql://am_replenishment_db_user:4M8xsThJDkrNgaL0siQaGN0kbx9ZPqhR@dpg-d6e55uv5r7bs73belrm0-a.virginia-postgres.render.com/am_replenishment_db"
)

# ==============================
# SHIPMENTS (Nexlev + Viomi)
# ==============================
ship_nexlev = pd.read_csv("data/input/fba_shipments_nexlev.csv")
ship_viomi = pd.read_csv("data/input/fba_shipments_viomi.csv")

shipments = pd.concat([ship_nexlev, ship_viomi], ignore_index=True)

shipments.to_sql(
    "shipments",
    engine,
    if_exists="replace",
    index=False
)

print("Shipments uploaded")

# ==============================
# INVENTORY LEDGER (Nexlev + Viomi)
# ==============================
ledger_nexlev = pd.read_csv("data/input/inventory_ledger_nexlev.csv")
ledger_viomi = pd.read_csv("data/input/inventory_ledger_viomi.csv")

ledger = pd.concat([ledger_nexlev, ledger_viomi], ignore_index=True)

ledger.to_sql(
    "inventory_ledger",
    engine,
    if_exists="replace",
    index=False
)

print("Inventory ledger uploaded")
print("✅ All data uploaded successfully")