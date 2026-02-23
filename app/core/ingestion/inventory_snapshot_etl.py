import pandas as pd
from sqlalchemy import text
from app.persistence.writers import get_engine


def build_inventory_snapshot():
    engine = get_engine()

    # 1️⃣ Read ledger
    query = """
        SELECT
  sku,
  fc,
  to_date(week || '-1', 'IYYY-IW-ID') AS week,
  ending_qty
FROM inventory_ledger
    """
    df = pd.read_sql(query, engine)

    if df.empty:
        print("⚠️ inventory_ledger is empty")
        return

    # 2️⃣ Aggregate (safety)
    snapshot = (
        df.groupby(["sku", "fc", "week"], as_index=False)
          .agg({"ending_qty": "sum"})
    )

    # 3️⃣ Load snapshot (replace per run)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE inventory_snapshot"))
        snapshot.to_sql(
            "inventory_snapshot",
            conn,
            if_exists="append",
            index=False,
            method="multi"
        )

    print(f"✅ inventory_snapshot loaded: {len(snapshot)} rows")


if __name__ == "__main__":
    build_inventory_snapshot()
