from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import pandas as pd
from app.config import DATABASE_URL


# -------------------------------------------------
# DATABASE ENGINE (SINGLE SOURCE)
# -------------------------------------------------
_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10
        )
    return _engine


# -------------------------------------------------
# GENERIC READ HELPERS
# -------------------------------------------------
def read_sql(query: str, params: dict | None = None) -> pd.DataFrame:
    engine = get_engine()
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params=params)


# -------------------------------------------------
# DOMAIN READERS
# -------------------------------------------------
def load_outward_shipments(week: str) -> pd.DataFrame:
    query = """
        SELECT invoice_no, sku, fc, qty_sent, ship_date, week
        FROM outward_shipments
        WHERE week = :week
    """
    return read_sql(query, {"week": week})


def load_inventory_ledger(week: str) -> pd.DataFrame:
    query = """
        SELECT sku, fc, sellable_qty, damaged_qty, recall_qty
        FROM inventory_ledger
        WHERE snapshot_week = :week
    """
    return read_sql(query, {"week": week})


def load_sales_velocity(weeks: list[str]) -> pd.DataFrame:
    query = """
        SELECT asin, sku, fc, week, units_sold
        FROM sales_velocity
        WHERE week = ANY(:weeks)
    """
    return read_sql(query, {"weeks": weeks})


def load_b2b_inventory(week: str) -> pd.DataFrame:
    query = """
        SELECT sku, qty, aging_days
        FROM b2b_inventory
        WHERE snapshot_week = :week
    """
    return read_sql(query, {"week": week})


def load_existing_replenishment(run_id: str) -> pd.DataFrame:
    query = """
        SELECT *
        FROM replenishment_lines
        WHERE run_id = :run_id
    """
    return read_sql(query, {"run_id": run_id})
