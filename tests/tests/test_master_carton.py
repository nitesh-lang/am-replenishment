"""
Tests for compute_recommended_qty — Master Carton Intelligence.

This is the purest business logic in the codebase: no I/O, no DB, no files.
Every edge case from the docstring is verified here.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.replenishment import compute_recommended_qty


class TestMasterCartonBasic:
    """Happy-path carton rounding."""

    def test_exact_multiple(self):
        """qty=80, carton=40 → 80, no break, 2 cartons, 0 excess."""
        r = compute_recommended_qty(80, 40, "IXD")
        assert r["recommended_qty"] == 80
        assert r["cartons_needed"] == 2
        assert r["excess_units"] == 0
        assert r["carton_break_flag"] is False

    def test_round_down_within_tolerance(self):
        """qty=41, carton=40 → remainder=1 (2.5% ≤ 10%) → round DOWN to 40."""
        r = compute_recommended_qty(41, 40, "IXD")
        assert r["recommended_qty"] == 40
        assert r["cartons_needed"] == 1
        assert r["excess_units"] == 0

    def test_round_up_normal(self):
        """qty=69, carton=40 → round UP to 80, excess=11."""
        r = compute_recommended_qty(69, 40, "IXD")
        assert r["recommended_qty"] == 80
        assert r["cartons_needed"] == 2
        assert r["excess_units"] == 11
        assert r["carton_break_flag"] is False  # 11/40 = 27.5% < 50%

    def test_round_up_small_qty(self):
        """qty=25, carton=40 → round UP to 40, excess=15 (37.5%)."""
        r = compute_recommended_qty(25, 40, "IXD")
        assert r["recommended_qty"] == 40
        assert r["cartons_needed"] == 1
        assert r["excess_units"] == 15
        assert r["carton_break_flag"] is False  # 15/40 = 37.5% < 50%

    def test_carton_break_flag(self):
        """qty=19, carton=40 → round UP to 40, excess=21 (52.5% > 50%) → flag True."""
        r = compute_recommended_qty(19, 40, "IXD")
        assert r["recommended_qty"] == 40
        assert r["cartons_needed"] == 1
        assert r["excess_units"] == 21
        assert r["carton_break_flag"] is True

    def test_boundary_exactly_50_pct(self):
        """qty=20, carton=40 → excess=20 (exactly 50%) → flag False (strictly >50%)."""
        r = compute_recommended_qty(20, 40, "IXD")
        assert r["recommended_qty"] == 40
        assert r["excess_units"] == 20
        assert r["carton_break_flag"] is False


class TestMasterCartonEdgeCases:
    """Zero, negative, and missing inputs."""

    def test_zero_qty(self):
        """Zero replenishment → passthrough, no cartons."""
        r = compute_recommended_qty(0, 40, "IXD")
        assert r["recommended_qty"] == 0
        assert r["cartons_needed"] == 0

    def test_zero_carton(self):
        """Zero carton size → passthrough."""
        r = compute_recommended_qty(50, 0, "IXD")
        assert r["recommended_qty"] == 50
        assert r["cartons_needed"] == 0

    def test_negative_carton(self):
        """Negative carton → passthrough."""
        r = compute_recommended_qty(50, -10, "IXD")
        assert r["recommended_qty"] == 50

    def test_negative_qty(self):
        """Negative qty → passthrough."""
        r = compute_recommended_qty(-5, 40, "IXD")
        assert r["recommended_qty"] == -5

    def test_none_carton(self):
        """None carton → passthrough."""
        r = compute_recommended_qty(50, None, "IXD")
        assert r["recommended_qty"] == 50

    def test_single_unit(self):
        """qty=1, carton=40 → remainder=1 (2.5% ≤ 10% tolerance) → round DOWN to 0."""
        r = compute_recommended_qty(1, 40, "IXD")
        assert r["recommended_qty"] == 0
        assert r["cartons_needed"] == 0
        assert r["excess_units"] == 0
        assert r["carton_break_flag"] is False

    def test_tolerance_boundary_exact_10_pct(self):
        """qty=44, carton=40 → remainder=4 (10% exactly). 4 ≤ 4.0 → round DOWN."""
        r = compute_recommended_qty(44, 40, "IXD")
        assert r["recommended_qty"] == 40
        assert r["cartons_needed"] == 1

    def test_tolerance_boundary_just_above(self):
        """qty=45, carton=40 → remainder=5 (12.5% > 10%) → round UP to 80."""
        r = compute_recommended_qty(45, 40, "IXD")
        assert r["recommended_qty"] == 80
        assert r["cartons_needed"] == 2


class TestMasterCartonLargeValues:
    """Realistic product quantities."""

    def test_large_qty(self):
        """qty=1000, carton=24 → 1000/24 = 41.67 → ceil=42, floor=41."""
        r = compute_recommended_qty(1000, 24, "IXD")
        # 41*24=984, remainder=16, tolerance=2.4, 16>2.4 → round up
        # 42*24=1008, excess=8, 8/24=33% < 50%
        assert r["recommended_qty"] == 1008
        assert r["cartons_needed"] == 42
        assert r["excess_units"] == 8
        assert r["carton_break_flag"] is False

    def test_carton_of_one(self):
        """carton=1 → always exact, never excess."""
        r = compute_recommended_qty(73, 1, "IXD")
        assert r["recommended_qty"] == 73
        assert r["cartons_needed"] == 73
        assert r["excess_units"] == 0
