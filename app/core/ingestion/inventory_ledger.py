import pandas as pd
from sqlalchemy import text
from app.persistence.writers import get_engine
from app.utils.week import to_week


def load_inventory_ledger(excel_path: str, snapshot_date: str):
    df = pd.read_excel(excel_path)

    # ---- Normalize column names ----
    df.columns = df.columns.str.strip()

    df = df.rename(columns={
        "MSKU": "sku",
        "Location": "fc",
        "Ending Warehouse Balance": "ending_qty",
    })

    # ---- Keep only valid rows ----
    df = df[["sku", "fc", "ending_qty"]]
    df = df.dropna(subset=["sku", "fc"])
    df["ending_qty"] = pd.to_numeric(df["ending_qty"], errors="coerce").fillna(0).astype(int)

    # ---- Add week ----
    df["week"] = to_week(pd.to_datetime(snapshot_date))

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM inventory_ledger"))
        df.to_sql(
            "inventory_ledger",
            conn,
            if_exists="append",
            index=False,
            method="multi"
        )

    print(f"✅ Inventory ledger loaded: {len(df)} rows | week {df['week'].iloc[0]}")


if __name__ == "__main__":
    import sys
    excel_path = sys.argv[1]
    snapshot_date = sys.argv[2]

    load_inventory_ledger(excel_path, snapshot_date)

