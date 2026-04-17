"""
Shared fixtures for AM Replenishment test suite.
All fixtures produce small, deterministic DataFrames that mirror the real
column structure so service functions can be tested without file I/O or DB.
"""
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


# ============================================================
# SHIPMENTS FIXTURE  (fc_planning / fc_final_allocation)
# ============================================================
@pytest.fixture
def sample_shipments():
    """
    3 SKUs, 2 FCs, 28 days of data  →  4 weeks exactly.
    SKU-A: 40 units at FC1, 20 at FC2
    SKU-B: 10 units at FC1
    SKU-C: 0 units (exists in ledger only)
    """
    base = datetime(2025, 3, 1)
    rows = []
    # SKU-A at FC1 — 10 units/week × 4 weeks = 40
    for w in range(4):
        rows.append({
            "Merchant SKU": "SKU-A",
            "FC": "FC1",
            "Shipped Quantity": 10,
            "Shipment Date": base + timedelta(weeks=w),
            "Sales Channel": "Amazon.in",
        })
    # SKU-A at FC2 — 5 units/week × 4 = 20
    for w in range(4):
        rows.append({
            "Merchant SKU": "SKU-A",
            "FC": "FC2",
            "Shipped Quantity": 5,
            "Shipment Date": base + timedelta(weeks=w),
            "Sales Channel": "Amazon.in",
        })
    # SKU-B at FC1 — 10 total across 4 weeks
    for w in range(4):
        rows.append({
            "Merchant SKU": "SKU-B",
            "FC": "FC1",
            "Shipped Quantity": 2.5,
            "Shipment Date": base + timedelta(weeks=w),
            "Sales Channel": "Amazon.in",
        })
    return pd.DataFrame(rows)


# ============================================================
# LEDGER FIXTURE
# ============================================================
@pytest.fixture
def sample_ledger():
    """
    Inventory on hand at each FC.
    SKU-A: FC1=50, FC2=10
    SKU-B: FC1=5
    SKU-C: FC1=100  (no sales → excess)
    """
    return pd.DataFrame([
        {"MSKU": "SKU-A", "Location": "FC1", "Ending Warehouse Balance": 50, "Disposition": "SELLABLE"},
        {"MSKU": "SKU-A", "Location": "FC2", "Ending Warehouse Balance": 10, "Disposition": "SELLABLE"},
        {"MSKU": "SKU-B", "Location": "FC1", "Ending Warehouse Balance": 5,  "Disposition": "SELLABLE"},
        {"MSKU": "SKU-C", "Location": "FC1", "Ending Warehouse Balance": 100,"Disposition": "SELLABLE"},
        # UNSELLABLE row — should be filtered out
        {"MSKU": "SKU-A", "Location": "FC1", "Ending Warehouse Balance": 999,"Disposition": "UNSELLABLE"},
    ])


# ============================================================
# MASTER FIXTURE (Nexlev-style)
# ============================================================
@pytest.fixture
def sample_master_nexlev():
    return pd.DataFrame([
        {"Model": "MOD-A", "SKU": "SKU-A", "ASIN": "ASIN-A", "Category": "Speaker",
         "Status": "Active", "Master Carton": 40, "Hazmat/non-Hazmat": "Non-IXD Non Hazmat",
         "Hazmat Type": "Non-Hazmat"},
        {"Model": "MOD-B", "SKU": "SKU-B", "ASIN": "ASIN-B", "Category": "Mic",
         "Status": "Active", "Master Carton": 24, "Hazmat/non-Hazmat": "IXD Hazmat",
         "Hazmat Type": "Lithium"},
        {"Model": "MOD-C", "SKU": "SKU-C", "ASIN": "ASIN-C", "Category": "Cable",
         "Status": "Inactive", "Master Carton": 0, "Hazmat/non-Hazmat": "Non-IXD Non Hazmat",
         "Hazmat Type": "Non-Hazmat"},
    ])


# ============================================================
# WEEKLY SALES FIXTURE
# ============================================================
@pytest.fixture
def sample_weekly_sales():
    """4 weeks of sales for MOD-A and MOD-B."""
    rows = []
    for w in [1, 2, 3, 4]:
        rows.append({"model": "MOD-A", "brand": "Nexlev", "week": f"Week {w}",
                      "units_sold": 20, "channel": "Amazon"})
        rows.append({"model": "MOD-B", "brand": "Nexlev", "week": f"Week {w}",
                      "units_sold": 5, "channel": "Amazon"})
    return pd.DataFrame(rows)


# ============================================================
# AMAZON INVENTORY FIXTURE
# ============================================================
@pytest.fixture
def sample_amazon_inventory():
    return pd.DataFrame([
        {"asin": "ASIN-A", "afn-total-quantity": 100, "afn-unsellable-quantity": 10,
         "afn-inbound-working-quantity": 5, "afn-inbound-shipped-quantity": 3},
        {"asin": "ASIN-B", "afn-total-quantity": 30, "afn-unsellable-quantity": 0,
         "afn-inbound-working-quantity": 0, "afn-inbound-shipped-quantity": 2},
        {"asin": "ASIN-C", "afn-total-quantity": 200, "afn-unsellable-quantity": 0,
         "afn-inbound-working-quantity": 0, "afn-inbound-shipped-quantity": 0},
    ])


# ============================================================
# WAREHOUSE INVENTORY FIXTURE
# ============================================================
@pytest.fixture
def sample_warehouse_inventory():
    return pd.DataFrame([
        {"Model": "MOD-A", "Channel": "AMPM", "Qty": 50},
        {"Model": "MOD-A", "Channel": "1P",   "Qty": 10},
        {"Model": "MOD-B", "Channel": "AMPM", "Qty": 20},
        {"Model": "MOD-C", "Channel": "AMPM", "Qty": 0},
    ])


# ============================================================
# CB REPLENISHMENT FIXTURES
# ============================================================
@pytest.fixture
def sample_cb_master():
    return pd.DataFrame([
        {"Brand": "Audio Array", "ASIN": "B0TEST1", "SKU": "FBA001", "Model": "AM-C1",
         "Hazmat Type": "IXD", "China In Transit": 0},
        {"Brand": "Audio Array", "ASIN": "B0TEST2", "SKU": "FBA002", "Model": "AM-C2",
         "Hazmat Type": "IXD", "China In Transit": 500},
        {"Brand": "Tonor",       "ASIN": "B0TEST3", "SKU": "FBA003", "Model": "TN-01",
         "Hazmat Type": "Non-IXD", "China In Transit": 0},
    ])


@pytest.fixture
def sample_cb_sales():
    """12 weeks of CB sales data."""
    rows = []
    for w in range(1, 13):
        rows.append({"brand": "Audio Array", "model": "AM-C1", "week": f"Week {w}",
                      "units_sold": 10, "channel": "1p Sales"})
        rows.append({"brand": "Audio Array", "model": "AM-C1", "week": f"Week {w}",
                      "units_sold": 5, "channel": "Amazon"})
        rows.append({"brand": "Audio Array", "model": "AM-C2", "week": f"Week {w}",
                      "units_sold": 3, "channel": "Amazon"})
        rows.append({"brand": "Tonor",       "model": "TN-01", "week": f"Week {w}",
                      "units_sold": 8, "channel": "1p Sales"})
    return pd.DataFrame(rows)


@pytest.fixture
def sample_cb_inventory():
    return pd.DataFrame([
        {"brand": "Audio Array", "model": "AM-C1", "channel": "1P",  "qty": 30},
        {"brand": "Audio Array", "model": "AM-C1", "channel": "AMPM","qty": 100},
        {"brand": "Audio Array", "model": "AM-C2", "channel": "1P",  "qty": 10},
        {"brand": "Tonor",       "model": "TN-01", "channel": "1P",  "qty": 50},
    ])


@pytest.fixture
def sample_cb_po():
    return pd.DataFrame([
        {"model": "AM-C1", "sku": "FBA001", "delivery status": "Open PO",   "accepted quantity": 20},
        {"model": "AM-C1", "sku": "FBA001", "delivery status": "In-Transit", "accepted quantity": 15},
        {"model": "TN-01", "sku": "FBA003", "delivery status": "Open PO",   "accepted quantity": 10},
    ])


# ============================================================
# CHINA REORDER FIXTURES
# ============================================================
@pytest.fixture
def sample_china_sales():
    rows = []
    for w in range(1, 13):
        rows.append({"brand": "nexlev", "model": "MOD-A", "week": f"Week {w}",
                      "units_sold": 15, "channel": "Amazon"})
        rows.append({"brand": "nexlev", "model": "MOD-B", "week": f"Week {w}",
                      "units_sold": 6, "channel": "Amazon"})
    return pd.DataFrame(rows)


@pytest.fixture
def sample_china_inventory():
    return pd.DataFrame([
        {"model": "MOD-A", "channel": "warehouse", "qty": 200},
        {"model": "MOD-A", "channel": "open order", "qty": 50},
        {"model": "MOD-A", "channel": "pipeline",   "qty": 30},
        {"model": "MOD-B", "channel": "warehouse", "qty": 10},
        {"model": "MOD-B", "channel": "open order", "qty": 0},
        {"model": "MOD-B", "channel": "pipeline",   "qty": 0},
    ])


# ============================================================
# DB MOCK HELPER
# ============================================================
@pytest.fixture
def mock_db_empty():
    """Mocks psycopg2 to return empty result set."""
    with patch("psycopg2.connect") as mock_conn:
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.description = [("model",), ("po_requirement",), ("remarks",)]
        conn.cursor.return_value = cursor
        mock_conn.return_value = conn
        # Also mock pd.read_sql to return empty DataFrame
        with patch("pandas.read_sql", return_value=pd.DataFrame(columns=["model", "po_requirement", "remarks"])):
            yield mock_conn
