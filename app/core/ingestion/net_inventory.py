import pandas as pd
from sqlalchemy import text
from app.persistence.writers import get_engine


def build_net_inventory():
    engine = get_engine()

    query = """
        SELECT
            sku,
            fc,
            week,
            ending_qty AS net_qty
        FROM inventory_snapshot
    """

    df = pd.read_sql(query, engine)

    if df.empty:
        print("⚠️ inventory_snapshot is empty")
        return

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE net_inventory"))
        df.to_sql(
            "net_inventory",
            conn,
            if_exists="append",
            index=False,
            method="multi"
        )

    print(f"✅ net_inventory loaded: {len(df)} rows")


if __name__ == "__main__":
    build_net_inventory()
