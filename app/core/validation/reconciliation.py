import pandas as pd


class ReconciliationError(Exception):
    """Raised when inventory reconciliation fails."""
    pass


# -------------------------------------------------
# BASIC RECONCILIATION
# Opening + In - Out = Closing
# -------------------------------------------------
def reconcile_inventory(
    opening_df: pd.DataFrame,
    inbound_df: pd.DataFrame,
    outbound_df: pd.DataFrame,
    closing_df: pd.DataFrame,
):
    """
    Reconciles inventory at SKU + FC level.

    Required columns:
    sku, fc, qty
    """

    def _prep(df: pd.DataFrame, name: str) -> pd.DataFrame:
        required = {"sku", "fc", "qty"}
        missing = required - set(df.columns)
        if missing:
            raise ReconciliationError(
                f"[{name}] Missing columns: {missing}"
            )

        return (
            df.groupby(["sku", "fc"], as_index=False)["qty"]
            .sum()
            .rename(columns={"qty": name})
        )

    opening = _prep(opening_df, "opening_qty")
    inbound = _prep(inbound_df, "inbound_qty")
    outbound = _prep(outbound_df, "outbound_qty")
    closing = _prep(closing_df, "closing_qty")

    # merge all
    recon = (
        opening
        .merge(inbound, on=["sku", "fc"], how="outer")
        .merge(outbound, on=["sku", "fc"], how="outer")
        .merge(closing, on=["sku", "fc"], how="outer")
        .fillna(0)
    )

    recon["calculated_closing"] = (
        recon["opening_qty"]
        + recon["inbound_qty"]
        - recon["outbound_qty"]
    )

    recon["delta"] = recon["closing_qty"] - recon["calculated_closing"]

    mismatches = recon[recon["delta"] != 0]

    if not mismatches.empty:
        raise ReconciliationError(
            "Inventory reconciliation failed.\n"
            f"{mismatches.head(20)}"
        )

    return True


# -------------------------------------------------
# LIGHTWEIGHT REPLENISHMENT CONSISTENCY CHECK
# -------------------------------------------------
def reconcile_replenishment_vs_stock(
    net_available_df: pd.DataFrame,
    replenishment_df: pd.DataFrame,
):
    """
    Ensures replenishment does not exceed logical bounds.
    """

    required_cols = {"sku", "fc", "net_available"}
    missing = required_cols - set(net_available_df.columns)
    if missing:
        raise ReconciliationError(
            f"Net inventory missing columns: {missing}"
        )

    rep_required = {"sku", "fc", "replenishment"}
    missing = rep_required - set(replenishment_df.columns)
    if missing:
        raise ReconciliationError(
            f"Replenishment missing columns: {missing}"
        )

    merged = (
        net_available_df
        .merge(replenishment_df, on=["sku", "fc"], how="left")
        .fillna(0)
    )

    invalid = merged[merged["replenishment"] < 0]

    if not invalid.empty:
        raise ReconciliationError(
            "Negative replenishment detected:\n"
            f"{invalid.head(10)}"
        )

    return True
