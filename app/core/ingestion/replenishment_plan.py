import pandas as pd
from sqlalchemy import text
from app.persistence.writers import get_engine

TARGET_WEEKS_OF_COVER = 4
AVG_WEEKLY_SALES = 10   # placeholder (replace later)


def build_replenishment_plan():
    engine = get_engine()

    df = pd.read_sql("""
        SELECT sku, fc, week, net_qty
        FROM net_inventory
    """, engine)

    if df.empty:
        print("⚠️ net_inventory empty")
        return

    df["target_qty"] = TARGET_WEEKS_OF_COVER * AVG_WEEKLY_SALES
    df["reorder_qty"] = (df["target_qty"] - df["net_qty"]).clip(lower=0)

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE replenishment_plan"))
        df.to_sql(
            "replenishment_plan",
            conn,
            if_exists="append",
            index=False,
            method="multi"
        )

    print(f"✅ replenishment_plan generated: {len(df)} rows")


if __name__ == "__main__":
    build_replenishment_plan()
