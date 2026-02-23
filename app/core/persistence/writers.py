from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
import pandas as pd
from app.persistence.readers import get_engine
from app.config import RUN_STATUS


# -------------------------------------------------
# RUN MANAGEMENT
# -------------------------------------------------
def create_replenishment_run(run_id: str, brand: str, week: str):
    engine = get_engine()
    query = """
        INSERT INTO replenishment_runs (run_id, brand, week, status)
        VALUES (:run_id, :brand, :week, :status)
    """
    with engine.begin() as conn:
        conn.execute(
            text(query),
            {
                "run_id": run_id,
                "brand": brand,
                "week": week,
                "status": RUN_STATUS["DRAFT"],
            },
        )


def update_run_status(run_id: str, status: str):
    engine = get_engine()
    query = """
        UPDATE replenishment_runs
        SET status = :status
        WHERE run_id = :run_id
    """
    with engine.begin() as conn:
        conn.execute(text(query), {"run_id": run_id, "status": status})


# -------------------------------------------------
# WRITE REPLENISHMENT OUTPUT
# -------------------------------------------------
def write_replenishment_lines(run_id: str, df: pd.DataFrame):
    """
    Writes final replenishment snapshot.
    This is an append-only operation per run.
    """
    engine = get_engine()

    df = df.copy()
    df["run_id"] = run_id

    try:
        df.to_sql(
            "replenishment_lines",
            engine,
            if_exists="append",
            index=False,
            method="multi",
            chunksize=500,
        )
    except IntegrityError as e:
        raise RuntimeError(
            "Duplicate replenishment lines detected. "
            "Run may already be locked."
        ) from e


# -------------------------------------------------
# OVERRIDE LOGGING
# -------------------------------------------------
def log_override(
    run_id: str,
    sku: str,
    fc: str,
    field_changed: str,
    old_value: int,
    new_value: int,
    reason: str,
    user_name: str,
):
    engine = get_engine()
    query = """
        INSERT INTO override_logs
        (run_id, sku, fc, field_changed, old_value, new_value, reason, user_name)
        VALUES
        (:run_id, :sku, :fc, :field_changed, :old_value, :new_value, :reason, :user_name)
    """
    with engine.begin() as conn:
        conn.execute(
            text(query),
            {
                "run_id": run_id,
                "sku": sku,
                "fc": fc,
                "field_changed": field_changed,
                "old_value": old_value,
                "new_value": new_value,
                "reason": reason,
                "user_name": user_name,
            },
        )
