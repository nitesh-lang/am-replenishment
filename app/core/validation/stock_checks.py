import pandas as pd
from app.config import AMAZON_FCS, VALIDATION_LIMITS


class StockValidationError(Exception):
    """Raised when stock validation fails."""
    pass


# -------------------------------------------------
# REQUIRED COLUMN CHECK
# -------------------------------------------------
def validate_required_columns(df: pd.DataFrame, required_cols: set, context: str):
    missing = required_cols - set(df.columns)
    if missing:
        raise StockValidationError(
            f"[{context}] Missing required columns: {missing}"
        )


# -------------------------------------------------
# FC VALIDATION
# -------------------------------------------------
def validate_fc_codes(df: pd.DataFrame):
    validate_required_columns(df, {"fc"}, "FC Validation")

    invalid_fcs = set(df["fc"].unique()) - set(AMAZON_FCS)
    if invalid_fcs:
        raise StockValidationError(
            f"Invalid FC codes detected: {invalid_fcs}"
        )


# -------------------------------------------------
# NEGATIVE STOCK CHECK
# -------------------------------------------------
def validate_non_negative_stock(df: pd.DataFrame):
    validate_required_columns(
        df,
        {"sellable_qty", "damaged_qty", "recall_qty"},
        "Stock Quantity Validation",
    )

    numeric_cols = ["sellable_qty", "damaged_qty", "recall_qty"]

    for col in numeric_cols:
        invalid = df[df[col] < VALIDATION_LIMITS["max_negative_stock"]]
        if not invalid.empty:
            raise StockValidationError(
                f"Negative values found in {col}:\n{invalid.head(10)}"
            )


# -------------------------------------------------
# SELLABLE ONLY CONTAMINATION CHECK
# -------------------------------------------------
def validate_sellable_only(df: pd.DataFrame):
    """
    Ensures non-sellable quantities are not mixed into sellable stock.
    """
    validate_required_columns(
        df,
        {"sellable_qty", "damaged_qty"},
        "Sellable Contamination Check",
    )

    contaminated = df[
        (df["sellable_qty"] > 0) & (df["damaged_qty"] > 0)
    ]

    if not contaminated.empty:
        raise StockValidationError(
            "Sellable stock contaminated with damaged quantities:\n"
            f"{contaminated.head(10)}"
        )


# -------------------------------------------------
# SKU + FC UNIQUENESS
# -------------------------------------------------
def validate_sku_fc_uniqueness(df: pd.DataFrame):
    validate_required_columns(df, {"sku", "fc"}, "SKU-FC Uniqueness")

    dupes = (
        df.groupby(["sku", "fc"])
        .size()
        .reset_index(name="count")
        .query("count > 1")
    )

    if not dupes.empty:
        raise StockValidationError(
            f"Duplicate SKU+FC rows detected:\n{dupes.head(10)}"
        )


# -------------------------------------------------
# MASTER STOCK VALIDATOR
# -------------------------------------------------
def validate_inventory_ledger(df_ledger: pd.DataFrame):
    """
    Runs all inventory validations.
    """
    validate_required_columns(
        df_ledger,
        {"sku", "fc", "sellable_qty", "damaged_qty", "recall_qty"},
        "Inventory Ledger",
    )

    validate_fc_codes(df_ledger)
    validate_non_negative_stock(df_ledger)
    validate_sellable_only(df_ledger)
    validate_sku_fc_uniqueness(df_ledger)
