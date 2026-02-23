import uuid
import sys
from datetime import datetime

from app.persistence.readers import (
    load_outward_shipments,
    load_inventory_ledger,
    load_sales_velocity,
    load_b2b_inventory,
)
from app.persistence.writers import (
    create_replenishment_run,
    write_replenishment_lines,
    update_run_status,
)

from app.validation.invoice_checks import (
    validate_invoice_duplicates,
    validate_invoice_quantities,
)
from app.validation.stock_checks import validate_inventory_ledger
from app.validation.reconciliation import reconcile_replenishment_vs_stock

from app.calculations.net_inventory import compute_net_inventory
from app.calculations.demand import (
    compute_avg_weekly_sales,
    compute_requirement,
)
from app.calculations.replenishment import compute_replenishment


# -------------------------------------------------
# MAIN WEEKLY RUNNER
# -------------------------------------------------
def run_weekly_replenishment(
    brand: str,
    week: str,
    target_weeks: int = 2,
):
    """
    Executes one full weekly replenishment run.
    """

    run_id = str(uuid.uuid4())
    print(f"\n🚀 Starting replenishment run: {run_id}")
    print(f"Brand: {brand} | Week: {week}\n")

    try:
        # -----------------------------------------
        # CREATE RUN
        # -----------------------------------------
        create_replenishment_run(run_id, brand, week)

        # -----------------------------------------
        # INGEST DATA
        # -----------------------------------------
        outward_df = load_outward_shipments(week)
        ledger_df = load_inventory_ledger(week)

        # last 8 weeks incl current
        year, wk = week.split("-")
        wk = int(wk)
        weeks = [
            f"{year}-{str(w).zfill(2)}"
            for w in range(wk - 7, wk + 1)
        ]

        sales_df = load_sales_velocity(weeks)
        b2b_df = load_b2b_inventory(week)

        # -----------------------------------------
        # VALIDATION LAYER
        # -----------------------------------------
        validate_invoice_duplicates(outward_df)
        validate_invoice_quantities(outward_df)

        validate_inventory_ledger(ledger_df)

        # -----------------------------------------
        # CALCULATIONS
        # -----------------------------------------
        net_inventory_df = compute_net_inventory(
            df_ledger=ledger_df,
            df_b2b=b2b_df,
        )

        avg_sales_df = compute_avg_weekly_sales(sales_df)
        demand_df = compute_requirement(
            avg_sales_df,
            target_weeks=target_weeks,
        )

        replenishment_df = compute_replenishment(
            demand_df=demand_df,
            net_inventory_df=net_inventory_df,
        )

        # -----------------------------------------
        # FINAL CONSISTENCY CHECK
        # -----------------------------------------
        reconcile_replenishment_vs_stock(
            net_available_df=net_inventory_df,
            replenishment_df=replenishment_df,
        )

        # -----------------------------------------
        # WRITE OUTPUT
        # -----------------------------------------
        write_replenishment_lines(run_id, replenishment_df)

        update_run_status(run_id, "locked")

        print("\n✅ Replenishment run completed successfully")
        print(f"Run ID: {run_id}")

    except Exception as e:
        print("\n❌ Replenishment run FAILED")
        print(str(e))

        try:
            update_run_status(run_id, "blocked")
        except Exception:
            pass

        sys.exit(1)


# -------------------------------------------------
# CLI ENTRYPOINT
# -------------------------------------------------
if __name__ == "__main__":
    """
    Example:
    python run_weekly.py Nexlev 2026-05 2
    """

    if len(sys.argv) < 3:
        print("Usage: python run_weekly.py <BRAND> <YYYY-WW> [TARGET_WEEKS]")
        sys.exit(1)

    brand = sys.argv[1]
    week = sys.argv[2]
    target_weeks = int(sys.argv[3]) if len(sys.argv) > 3 else 2

    run_weekly_replenishment(
        brand=brand,
        week=week,
        target_weeks=target_weeks,
    )
