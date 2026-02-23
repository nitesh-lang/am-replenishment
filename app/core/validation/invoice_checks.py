import pandas as pd


class InvoiceValidationError(Exception):
    """Raised when invoice validation fails."""
    pass


# -------------------------------------------------
# CORE VALIDATION: DUPLICATE INVOICE + SKU
# -------------------------------------------------
def validate_invoice_duplicates(df_outward: pd.DataFrame):
    """
    Prevents re-sending the same invoice + SKU.
    This is NON-NEGOTIABLE logic.
    """

    required_cols = {"invoice_no", "sku"}
    missing = required_cols - set(df_outward.columns)

    if missing:
        raise InvoiceValidationError(
            f"Missing required columns in outward data: {missing}"
        )

    dupes = (
        df_outward
        .groupby(["invoice_no", "sku"])
        .size()
        .reset_index(name="count")
        .query("count > 1")
    )

    if not dupes.empty:
        raise InvoiceValidationError(
            f"Duplicate invoice+SKU detected:\n{dupes.head(10)}"
        )


# -------------------------------------------------
# BLOCK PREVIOUSLY SHIPPED SKUs
# -------------------------------------------------
def block_previously_shipped(
    df_candidate: pd.DataFrame,
    df_outward_history: pd.DataFrame
) -> pd.DataFrame:
    """
    Removes SKUs already sent in previous weeks.
    Ensures weekly replenishment does not resend stock.
    """

    key_cols = ["invoice_no", "sku"]

    for col in key_cols:
        if col not in df_candidate.columns:
            raise InvoiceValidationError(
                f"Candidate data missing column: {col}"
            )

    blocked_keys = set(
        zip(
            df_outward_history["invoice_no"],
            df_outward_history["sku"]
        )
    )

    def is_blocked(row):
        return (row["invoice_no"], row["sku"]) in blocked_keys

    df_candidate = df_candidate.copy()
    df_candidate["is_blocked"] = df_candidate.apply(is_blocked, axis=1)

    return df_candidate[df_candidate["is_blocked"] is False].drop(
        columns=["is_blocked"]
    )


# -------------------------------------------------
# SANITY CHECK: POSITIVE QUANTITIES
# -------------------------------------------------
def validate_invoice_quantities(df_outward: pd.DataFrame):
    if "qty_sent" not in df_outward.columns:
        raise InvoiceValidationError("Missing qty_sent column")

    invalid = df_outward[df_outward["qty_sent"] <= 0]

    if not invalid.empty:
        raise InvoiceValidationError(
            f"Invalid qty_sent detected:\n{invalid.head(10)}"
        )
