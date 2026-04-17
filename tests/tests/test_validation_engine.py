"""
Tests for validation_engine.py — data integrity checks.

All functions are pure (DataFrame in → dict out), so no mocking needed.
"""
import pytest
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.validation_engine import (
    _check_no_nulls,
    _check_no_negative,
    validate_shipments,
    validate_ledger,
    validate_fc_plan,
    run_full_validation,
)


# ============================================================
# LOW-LEVEL HELPERS
# ============================================================

class TestCheckNoNulls:

    def test_clean_data_passes(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        result = _check_no_nulls(df, ["a", "b"])
        assert result["passed"] is True
        assert result["issues"] == []

    def test_null_detected(self):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
        result = _check_no_nulls(df, ["a", "b"])
        assert result["passed"] is False
        assert len(result["issues"]) == 1
        assert "a" in result["issues"][0]

    def test_multiple_null_columns(self):
        df = pd.DataFrame({"a": [None], "b": [None]})
        result = _check_no_nulls(df, ["a", "b"])
        assert len(result["issues"]) == 2


class TestCheckNoNegative:

    def test_positive_passes(self):
        df = pd.DataFrame({"x": [0, 1, 100]})
        result = _check_no_negative(df, ["x"])
        assert result["passed"] is True

    def test_negative_fails(self):
        df = pd.DataFrame({"x": [10, -1, 5]})
        result = _check_no_negative(df, ["x"])
        assert result["passed"] is False

    def test_zero_is_ok(self):
        df = pd.DataFrame({"x": [0, 0, 0]})
        result = _check_no_negative(df, ["x"])
        assert result["passed"] is True


# ============================================================
# SHIPMENT VALIDATION
# ============================================================

class TestValidateShipments:

    def test_valid_shipments(self, sample_shipments):
        ship = sample_shipments.rename(columns={"Merchant SKU": "sku"})
        report = validate_shipments(ship)
        assert report["status"] == "PASS"
        assert report["row_count"] == 12
        assert report["unique_skus"] == 2  # SKU-A and SKU-B

    def test_negative_qty_fails(self, sample_shipments):
        ship = sample_shipments.rename(columns={"Merchant SKU": "sku"})
        ship.loc[0, "Shipped Quantity"] = -5
        report = validate_shipments(ship)
        assert report["status"] == "FAIL"


# ============================================================
# LEDGER VALIDATION
# ============================================================

class TestValidateLedger:

    def test_valid_ledger(self, sample_ledger):
        report = validate_ledger(sample_ledger)
        assert report["status"] == "PASS"
        assert report["unique_skus"] == 3

    def test_negative_balance_fails(self, sample_ledger):
        sample_ledger.loc[0, "Ending Warehouse Balance"] = -10
        report = validate_ledger(sample_ledger)
        assert report["status"] == "FAIL"


# ============================================================
# FC PLAN VALIDATION
# ============================================================

class TestValidateFcPlan:

    def test_valid_plan(self):
        df = pd.DataFrame({
            "weekly_velocity": [10.0, 5.0],
            "fc_inventory": [50, 20],
            "required_units": [80, 40],
            "fc_shortfall": [30, 20],
        })
        report = validate_fc_plan(df)
        assert report["status"] == "PASS"

    def test_shortfall_exceeds_required_fails(self):
        """Logical error: shortfall > required units."""
        df = pd.DataFrame({
            "weekly_velocity": [10.0],
            "fc_inventory": [5],
            "required_units": [80],
            "fc_shortfall": [100],  # > 80 — illogical
        })
        report = validate_fc_plan(df)
        assert report["status"] == "FAIL"
        assert any("Shortfall greater" in i for i in report["logical_issues"])

    def test_null_velocity_fails(self):
        df = pd.DataFrame({
            "weekly_velocity": [None],
            "fc_inventory": [50],
            "required_units": [80],
            "fc_shortfall": [30],
        })
        report = validate_fc_plan(df)
        assert report["status"] == "FAIL"

    def test_negative_coverage_weeks(self):
        df = pd.DataFrame({
            "weekly_velocity": [10.0],
            "fc_inventory": [50],
            "required_units": [80],
            "fc_shortfall": [30],
            "coverage_weeks": [-2],
        })
        report = validate_fc_plan(df)
        assert report["status"] == "FAIL"


# ============================================================
# FULL VALIDATION
# ============================================================

class TestFullValidation:

    def test_all_pass(self, sample_shipments, sample_ledger):
        ship = sample_shipments.rename(columns={"Merchant SKU": "sku"})
        fc_plan = pd.DataFrame({
            "weekly_velocity": [10.0, 5.0],
            "fc_inventory": [50, 20],
            "required_units": [80, 40],
            "fc_shortfall": [30, 20],
        })
        report = run_full_validation(ship, sample_ledger, fc_plan)
        assert report["overall_status"] == "PASS"

    def test_one_failure_cascades(self, sample_shipments, sample_ledger):
        ship = sample_shipments.rename(columns={"Merchant SKU": "sku"})
        ship.loc[0, "Shipped Quantity"] = -1  # Cause shipment failure
        fc_plan = pd.DataFrame({
            "weekly_velocity": [10.0],
            "fc_inventory": [50],
            "required_units": [80],
            "fc_shortfall": [30],
        })
        report = run_full_validation(ship, sample_ledger, fc_plan)
        assert report["overall_status"] == "FAIL"
        assert report["shipments"]["status"] == "FAIL"
        assert report["ledger"]["status"] == "PASS"
