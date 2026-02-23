import pandas as pd
from app.config import (
    ROUND_TO_MASTER_CARTON,
    MAX_REPLENISHMENT_MULTIPLIER,
)


class ReplenishmentError(Exception):
    """Raised when replenishment calculation fails."""
    pass


# -------------------------------------------------
# MASTER CARTON ROUNDING
# -------------------------------------------------
def round_to_master_carton(qty: int, carton_size: int) -> int:
    if carton_size <= 0:
        return qty

    if qty <= 0:
        return 0

    return int(((qty + carton_size - 1) // carton_size) * carton_size)


# -------------------------------------------------
# CORE REPLENISHMENT CALCULATION
# -------------------------------------------------
def compute_replenishment(
    demand_df: pd.DataFrame,
    net_inventory_df: pd.DataFrame,
    master_carton_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Replenishment =
        max(0, Requirement - Net Available)

    Applies:
    - Safety caps
    - Master carton rounding
    """

    required_demand = {"sku", "fc", "avg_weekly_sales", "requirement"}
    required_net = {"sku", "fc", "net_available"}

    if not required_demand.issubset(demand_df.columns):
        raise ReplenishmentError(
            f"Demand DF missing columns: {required_demand - set(demand_df.columns)}"
        )

    if not required_net.issubset(net_inventory_df.columns):
        raise ReplenishmentError(
            f"Net inventory DF missing columns: {required_net - set(net_inventory_df.columns)}"
        )

    # merge demand & inventory
    df = (
        demand_df
        .merge(
            net_inventory_df[["sku", "fc", "net_available"]],
            on=["sku", "fc"],
            how="left",
        )
        .fillna({"net_available": 0})
    )

    # base replenishment
    df["replenishment_raw"] = (
        df["requirement"] - df["net_available"]
    )

    df["replenishment_raw"] = df["replenishment_raw"].clip(lower=0)

    # safety cap: avoid crazy sends
    df["max_allowed"] = (
        df["avg_weekly_sales"] * MAX_REPLENISHMENT_MULTIPLIER
    ).round().astype(int)

    df["replenishment_capped"] = df[
        ["replenishment_raw", "max_allowed"]
    ].min(axis=1)

    # master carton rounding
    if ROUND_TO_MASTER_CARTON and master_carton_df is not None:
        if not {"sku", "master_carton"}.issubset(master_carton_df.columns):
            raise ReplenishmentError(
                "Master carton DF missing required columns"
            )

        df = df.merge(
            master_carton_df[["sku", "master_carton"]],
            on="sku",
            how="left",
        ).fillna({"master_carton": 0})

        df["replenishment"] = df.apply(
            lambda r: round_to_master_carton(
                int(r["replenishment_capped"]),
                int(r["master_carton"]),
            ),
            axis=1,
        )
    else:
        df["replenishment"] = df["replenishment_capped"]

    # final sanity
    df["replenishment"] = df["replenishment"].clip(lower=0).astype(int)

    return df[
        [
            "sku",
            "fc",
            "avg_weekly_sales",
            "requirement",
            "net_available",
            "replenishment",
        ]
    ]
