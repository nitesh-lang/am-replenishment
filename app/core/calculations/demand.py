import pandas as pd
from app.config import SALES_LOOKBACK_WEEKS, DEFAULT_TARGET_WEEKS


class DemandCalculationError(Exception):
    """Raised when demand calculation fails."""
    pass


# -------------------------------------------------
# AVERAGE WEEKLY SALES (2 MONTHS)
# -------------------------------------------------
def compute_avg_weekly_sales(df_sales: pd.DataFrame) -> pd.DataFrame:
    """
    Computes average weekly sales per SKU + FC
    using last N weeks (default = 8).
    """

    required = {"sku", "fc", "week", "units_sold"}
    missing = required - set(df_sales.columns)
    if missing:
        raise DemandCalculationError(
            f"Sales data missing columns: {missing}"
        )

    # ensure only last N weeks are used
    df = df_sales.copy()
    df = df.sort_values("week").groupby(
        ["sku", "fc"], as_index=False
    ).tail(SALES_LOOKBACK_WEEKS)

    avg = (
        df.groupby(["sku", "fc"], as_index=False)["units_sold"]
        .mean()
        .rename(columns={"units_sold": "avg_weekly_sales"})
    )

    return avg


# -------------------------------------------------
# REQUIREMENT CALCULATION
# -------------------------------------------------
def compute_requirement(
    avg_sales_df: pd.DataFrame,
    target_weeks: int | None = None,
) -> pd.DataFrame:
    """
    Requirement = Avg Weekly Sales × Target Weeks
    """

    if target_weeks is None:
        target_weeks = DEFAULT_TARGET_WEEKS

    if target_weeks <= 0:
        raise DemandCalculationError(
            "Target weeks must be positive"
        )

    if "avg_weekly_sales" not in avg_sales_df.columns:
        raise DemandCalculationError(
            "avg_weekly_sales column missing"
        )

    df = avg_sales_df.copy()
    df["requirement"] = (
        df["avg_weekly_sales"] * target_weeks
    ).round().astype(int)

    return df[
        [
            "sku",
            "fc",
            "avg_weekly_sales",
            "requirement",
        ]
    ]
