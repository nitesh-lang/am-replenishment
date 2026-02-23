import pandas as pd
from app.config import B2B_MAX_AGE_DAYS, B2B_WEIGHT_FACTOR


class NetInventoryError(Exception):
    """Raised when net inventory calculation fails."""
    pass


# -------------------------------------------------
# B2B STOCK WEIGHTING
# -------------------------------------------------
def apply_b2b_weighting(df_b2b: pd.DataFrame) -> pd.DataFrame:
    """
    Applies aging-based weighting to B2B stock.
    Older stock is discounted or ignored.
    """

    required = {"sku", "qty", "aging_days"}
    missing = required - set(df_b2b.columns)
    if missing:
        raise NetInventoryError(
            f"B2B inventory missing columns: {missing}"
        )

    df = df_b2b.copy()

    # ignore very old B2B stock
    df.loc[df["aging_days"] > B2B_MAX_AGE_DAYS, "qty"] = 0

    # apply confidence weighting
    df["b2b_effective_qty"] = (df["qty"] * B2B_WEIGHT_FACTOR).astype(int)

    return (
        df.groupby("sku", as_index=False)["b2b_effective_qty"]
        .sum()
    )


# -------------------------------------------------
# AZ INVENTORY AGGREGATION
# -------------------------------------------------
def aggregate_az_inventory(df_ledger: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates Amazon FC sellable inventory.
    """

    required = {"sku", "fc", "sellable_qty", "recall_qty"}
    missing = required - set(df_ledger.columns)
    if missing:
        raise NetInventoryError(
            f"Inventory ledger missing columns: {missing}"
        )

    return (
        df_ledger
        .groupby(["sku", "fc"], as_index=False)
        .agg(
            az_sellable=("sellable_qty", "sum"),
            recall=("recall_qty", "sum"),
        )
    )


# -------------------------------------------------
# NET AVAILABLE INVENTORY
# -------------------------------------------------
def compute_net_inventory(
    df_ledger: pd.DataFrame,
    df_b2b: pd.DataFrame | None = None,
    df_eb: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Computes true net available inventory per SKU + FC.

    Net Available =
        AZ Sellable
      + EB Stock (optional)
      + B2B Stock (weighted)
      - Recall
    """

    az = aggregate_az_inventory(df_ledger)

    # EB stock (optional, SKU-level)
    if df_eb is not None:
        if not {"sku", "eb_stock"}.issubset(df_eb.columns):
            raise NetInventoryError(
                "EB stock missing required columns"
            )

        az = az.merge(
            df_eb.groupby("sku", as_index=False)["eb_stock"].sum(),
            on="sku",
            how="left",
        )
    else:
        az["eb_stock"] = 0

    # B2B stock (optional, SKU-level)
    if df_b2b is not None and not df_b2b.empty:
        b2b = apply_b2b_weighting(df_b2b)
        az = az.merge(b2b, on="sku", how="left")
    else:
        az["b2b_effective_qty"] = 0

    az = az.fillna(0)

    az["net_available"] = (
        az["az_sellable"]
        + az["eb_stock"]
        + az["b2b_effective_qty"]
        - az["recall"]
    )

    # final safety
    az["net_available"] = az["net_available"].clip(lower=0)

    return az[
        [
            "sku",
            "fc",
            "az_sellable",
            "eb_stock",
            "b2b_effective_qty",
            "recall",
            "net_available",
        ]
    ]
