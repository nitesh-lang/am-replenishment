import pandas as pd
from sqlalchemy import text
from app.persistence.writers import get_engine
from app.utils.week import to_week

def load_outward_shipments(excel_path: str):
    df = pd.read_excel(excel_path)

    df = df.rename(columns={
        "INVOICE NO": "invoice_no",
        "MATERIAL CODE": "sku",
        "CONSIGNEE PLACE": "fc",
        "DISPATCHED DATE": "ship_date"
    })

    df["qty_sent"] = 1  # 🔴 change later if qty column exists
    df["ship_date"] = pd.to_datetime(df["ship_date"])
    df["week"] = df["ship_date"].apply(to_week)

    df = df[[
        "invoice_no",
        "sku",
        "fc",
        "qty_sent",
        "ship_date",
        "week"
    ]]

    engine = get_engine()
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(
                text("""
                INSERT INTO outward_shipments
                (invoice_no, sku, fc, qty_sent, ship_date, week)
                VALUES (:invoice_no, :sku, :fc, :qty_sent, :ship_date, :week)
                ON CONFLICT (invoice_no, sku, fc) DO NOTHING
                """),
                row.to_dict()
            )

    print(f"✅ Loaded {len(df)} outward shipment rows")
