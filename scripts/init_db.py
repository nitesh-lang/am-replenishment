from sqlalchemy import create_engine, text
from app.config import DATABASE_URL

engine = create_engine(DATABASE_URL)

DDL = """
-- ===============================
-- SOURCE TABLES
-- ===============================

CREATE TABLE IF NOT EXISTS outward_shipments (
    invoice_no TEXT,
    sku TEXT,
    fc TEXT,
    qty_sent INTEGER,
    ship_date DATE,
    week TEXT
);

CREATE TABLE IF NOT EXISTS inventory_ledger (
    sku TEXT,
    fc TEXT,
    sellable_qty INTEGER,
    damaged_qty INTEGER,
    recall_qty INTEGER,
    week TEXT
);

CREATE TABLE IF NOT EXISTS sales_velocity (
    sku TEXT,
    fc TEXT,
    week TEXT,
    units_sold INTEGER
);

CREATE TABLE IF NOT EXISTS b2b_inventory (
    sku TEXT,
    qty INTEGER,
    aging_days INTEGER,
    week TEXT
);

-- ===============================
-- OUTPUT TABLES
-- ===============================

CREATE TABLE IF NOT EXISTS replenishment_runs (
    run_id UUID PRIMARY KEY,
    brand TEXT NOT NULL,
    week TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS replenishment_lines (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES replenishment_runs(run_id),
    sku TEXT NOT NULL,
    fc TEXT NOT NULL,
    avg_weekly_sales INTEGER,
    requirement INTEGER,
    net_available INTEGER,
    replenishment INTEGER
);
"""

with engine.begin() as conn:
    for stmt in DDL.split(";"):
        if stmt.strip():
            conn.execute(text(stmt))

print("✅ ALL tables initialized")
