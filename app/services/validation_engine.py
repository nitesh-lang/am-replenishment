import pandas as pd
from typing import Dict, Any


# ==========================================================
# GENERIC NUMERIC CHECK
# ==========================================================

def _check_no_nulls(df: pd.DataFrame, cols: list) -> Dict:
    issues = []
    for col in cols:
        if df[col].isna().sum() > 0:
            issues.append(f"Null values found in {col}")
    return {"passed": len(issues) == 0, "issues": issues}


def _check_no_negative(df: pd.DataFrame, cols: list) -> Dict:
    issues = []
    for col in cols:
        if (df[col] < 0).any():
            issues.append(f"Negative values found in {col}")
    return {"passed": len(issues) == 0, "issues": issues}


# ==========================================================
# SHIPMENT VALIDATION
# ==========================================================

def validate_shipments(shipments: pd.DataFrame) -> Dict[str, Any]:
    report = {}

    report["row_count"] = len(shipments)
    report["total_units"] = shipments["Shipped Quantity"].sum()
    report["unique_skus"] = shipments["sku"].nunique()
    report["min_date"] = shipments["Shipment Date"].min()
    report["max_date"] = shipments["Shipment Date"].max()

    numeric_check = _check_no_negative(shipments, ["Shipped Quantity"])

    report["numeric_integrity"] = numeric_check
    report["status"] = "PASS" if numeric_check["passed"] else "FAIL"

    return report


# ==========================================================
# LEDGER VALIDATION
# ==========================================================

def validate_ledger(ledger: pd.DataFrame) -> Dict[str, Any]:
    report = {}

    report["row_count"] = len(ledger)
    report["total_inventory"] = ledger["Ending Warehouse Balance"].sum()
    report["unique_skus"] = ledger["MSKU"].nunique()

    numeric_check = _check_no_negative(
        ledger,
        ["Ending Warehouse Balance"]
    )

    report["numeric_integrity"] = numeric_check
    report["status"] = "PASS" if numeric_check["passed"] else "FAIL"

    return report


# ==========================================================
# FC PLAN VALIDATION
# ==========================================================

def validate_fc_plan(df: pd.DataFrame) -> Dict[str, Any]:
    report = {}

    required_cols = [
        "weekly_velocity",
        "fc_inventory",
        "required_units",
        "fc_shortfall",
    ]

    # Null check
    null_check = _check_no_nulls(df, required_cols)

    # Negative check
    negative_check = _check_no_negative(df, required_cols)

    # Logical consistency
    logical_issues = []

    if (df["fc_shortfall"] > df["required_units"]).any():
        logical_issues.append("Shortfall greater than required units")

    if (df["required_units"] < 0).any():
        logical_issues.append("Required units negative")

    # Coverage sanity
    if "coverage_weeks" in df.columns:
        if (df["coverage_weeks"] < 0).any():
            logical_issues.append("Coverage weeks negative")

    report["row_count"] = len(df)
    report["total_required"] = df["required_units"].sum()
    report["total_inventory"] = df["fc_inventory"].sum()
    report["total_shortfall"] = df["fc_shortfall"].sum()

    report["null_check"] = null_check
    report["negative_check"] = negative_check
    report["logical_issues"] = logical_issues

    report["status"] = (
        "PASS"
        if null_check["passed"]
        and negative_check["passed"]
        and len(logical_issues) == 0
        else "FAIL"
    )

    return report


# ==========================================================
# MASTER VALIDATION WRAPPER
# ==========================================================

def run_full_validation(
    shipments: pd.DataFrame,
    ledger: pd.DataFrame,
    fc_plan: pd.DataFrame,
) -> Dict[str, Any]:

    shipment_report = validate_shipments(shipments)
    ledger_report = validate_ledger(ledger)
    fc_plan_report = validate_fc_plan(fc_plan)

    overall_status = (
        "PASS"
        if shipment_report["status"] == "PASS"
        and ledger_report["status"] == "PASS"
        and fc_plan_report["status"] == "PASS"
        else "FAIL"
    )

    return {
        "overall_status": overall_status,
        "shipments": shipment_report,
        "ledger": ledger_report,
        "fc_plan": fc_plan_report,
    }