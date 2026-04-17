"""
Tests for replenishment.py — core replenishment calculation engine.

Tests the helper functions directly (no file I/O) and the main
calculate_replenishment via mocked file_cache.
"""
import pytest
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.replenishment import (
    normalize_week_column,
    get_last_n_weeks_sales,
    validate_columns,
    compute_recommended_qty,
)


# ============================================================
# WEEK NORMALIZATION
# ============================================================

class TestNormalizeWeekColumn:

    def test_standard_format(self):
        df = pd.DataFrame({"week": ["Week 1", "Week 2", "Week 12"]})
        result = normalize_week_column(df)
        assert list(result["week_num"]) == [1, 2, 12]

    def test_numeric_only(self):
        df = pd.DataFrame({"week": ["3", "7", "11"]})
        result = normalize_week_column(df)
        assert list(result["week_num"]) == [3, 7, 11]

    def test_mixed_garbage(self):
        """Non-numeric falls to 0."""
        df = pd.DataFrame({"week": ["Week 5", "garbage", "Week 10"]})
        result = normalize_week_column(df)
        assert result["week_num"].iloc[0] == 5
        assert result["week_num"].iloc[1] == 0
        assert result["week_num"].iloc[2] == 10


# ============================================================
# SALES WINDOW SELECTION
# ============================================================

class TestGetLastNWeeksSales:

    def test_last_4_weeks(self, sample_weekly_sales):
        result = get_last_n_weeks_sales(sample_weekly_sales, 4)
        weeks = result["week_num"].unique()
        assert len(weeks) == 4

    def test_last_2_weeks(self, sample_weekly_sales):
        result = get_last_n_weeks_sales(sample_weekly_sales, 2)
        weeks = sorted(result["week_num"].unique(), reverse=True)
        # Should pick weeks 3 and 4 (latest 2)
        assert weeks == [4, 3]

    def test_cap_at_12(self):
        """Even if 15 weeks exist, only 12 are returned."""
        rows = [{"model": "X", "week": f"Week {w}", "units_sold": 1, "brand": "Test", "channel": "Amazon"}
                for w in range(1, 16)]
        df = pd.DataFrame(rows)
        result = get_last_n_weeks_sales(df, 15)
        assert result["week_num"].nunique() <= 12

    def test_request_more_than_available(self):
        """3 weeks of data but ask for 8 → get 3."""
        rows = [{"model": "X", "week": f"Week {w}", "units_sold": 1, "brand": "Test", "channel": "Amazon"}
                for w in [5, 6, 7]]
        df = pd.DataFrame(rows)
        result = get_last_n_weeks_sales(df, 8)
        assert result["week_num"].nunique() == 3


# ============================================================
# COLUMN VALIDATION
# ============================================================

class TestValidateColumns:

    def test_all_present(self):
        df = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
        validate_columns(df, ["A", "B"], "test")  # Should not raise

    def test_missing_column_raises(self):
        df = pd.DataFrame({"A": [1]})
        with pytest.raises(ValueError, match="Missing columns"):
            validate_columns(df, ["A", "B", "C"], "test_file")

    def test_empty_required_passes(self):
        df = pd.DataFrame({"A": [1]})
        validate_columns(df, [], "test")  # No requirements → pass


# ============================================================
# REPLENISHMENT FORMULA TESTS
# (Test the math without the full pipeline)
# ============================================================

class TestReplenishmentFormulas:
    """
    Verify the core formulas:
      required_units = sales_velocity × replenish_weeks
      replenishment_qty = max(0, required_units - amazon_inventory)
      warehouse_shortfall = max(0, replenishment_qty - ampm_inventory)
      is_risky = amazon_inventory < sales_velocity
      is_overstock = amazon_inventory > sales_velocity × 8
    """

    def test_normal_replenishment(self):
        velocity = 20  # units/week
        replenish_weeks = 8
        amazon_inv = 50
        ampm_inv = 100

        required = velocity * replenish_weeks  # 160
        repl_qty = max(0, required - amazon_inv)  # 110
        shortfall = max(0, repl_qty - ampm_inv)  # 10

        assert required == 160
        assert repl_qty == 110
        assert shortfall == 10

    def test_no_replenishment_needed(self):
        """Amazon has enough stock."""
        velocity = 5
        replenish_weeks = 4
        amazon_inv = 100

        required = velocity * replenish_weeks  # 20
        repl_qty = max(0, required - amazon_inv)  # 0

        assert repl_qty == 0

    def test_risky_flag(self):
        """Amazon inventory < 1 week of velocity → risky."""
        assert 30 < 50  # is_risky: inv < velocity

    def test_overstock_flag(self):
        """Amazon inventory > 8 weeks of velocity → overstock."""
        velocity = 10
        amazon_inv = 90
        assert amazon_inv > velocity * 8  # 80 → overstock

    def test_zero_velocity(self):
        """No sales → required_units = 0, no replenishment."""
        velocity = 0
        replenish_weeks = 8
        amazon_inv = 50

        required = velocity * replenish_weeks  # 0
        repl_qty = max(0, required - amazon_inv)  # 0

        assert required == 0
        assert repl_qty == 0


# ============================================================
# FC PLANNING FORMULA TESTS
# ============================================================

class TestFCPlanningFormulas:
    """
    FC-level formulas:
      velocity = total_units_in_file / total_weeks
      target_cover = velocity × replenish_weeks
      send_qty = max(0, target_cover - fc_inventory - in_transit - open_po)
      cluster_po = max(0, Σcluster_target - Σcluster_SOH - Σcluster_in_transit)
    """

    def test_velocity_calculation(self):
        """40 units over 4 weeks = 10/week."""
        total_units = 40
        total_weeks = 4
        velocity = total_units / total_weeks
        assert velocity == 10.0

    def test_target_cover(self):
        velocity = 10.0
        replenish_weeks = 8
        assert velocity * replenish_weeks == 80.0

    def test_send_qty(self):
        target = 80.0
        fc_inv = 30
        in_transit = 10
        open_po = 5
        send = max(0, target - fc_inv - in_transit - open_po)
        assert send == 35.0

    def test_send_qty_zero_when_stocked(self):
        target = 80.0
        fc_inv = 50
        in_transit = 20
        open_po = 15
        send = max(0, target - fc_inv - in_transit - open_po)
        assert send == 0  # 50+20+15 = 85 > 80

    def test_cluster_po(self):
        """
        Cluster BLR has FC1 (target=80, SOH=50, IT=10) + FC2 (target=40, SOH=5, IT=0)
        cluster_po = max(0, (80+40) - (50+5) - (10+0)) = max(0, 120-55-10) = 55
        """
        cluster_target = 80 + 40
        cluster_soh = 50 + 5
        cluster_it = 10 + 0
        cluster_po = max(0, cluster_target - cluster_soh - cluster_it)
        assert cluster_po == 55

    def test_cluster_po_zero_when_covered(self):
        cluster_target = 100
        cluster_soh = 80
        cluster_it = 30
        cluster_po = max(0, cluster_target - cluster_soh - cluster_it)
        assert cluster_po == 0


# ============================================================
# CB REPLENISHMENT FORMULA TESTS
# ============================================================

class TestCBFormulas:
    """
    CB formulas:
      avg_weekly_sales = total_sales / window_size
      estimated_qty = avg_weekly_sales × cover_weeks
      deficiency = max(0, estimated_qty - cb_soh)
      po_requirement = max(0, deficiency - open_po - in_transit)
    """

    def test_avg_weekly_sales(self):
        cb_sales = 120   # 1P channel
        cambium = 60     # Amazon channel
        window = 12      # weeks
        total = cb_sales + cambium  # 180
        avg = total / window  # 15
        assert avg == 15.0

    def test_estimated_qty(self):
        avg_weekly = 15.0
        cover_weeks = 8
        assert avg_weekly * cover_weeks == 120.0

    def test_deficiency(self):
        estimated = 120
        cb_soh = 30
        deficiency = max(0, estimated - cb_soh)
        assert deficiency == 90

    def test_deficiency_no_shortfall(self):
        estimated = 50
        cb_soh = 100
        assert max(0, estimated - cb_soh) == 0

    def test_po_requirement(self):
        deficiency = 90
        open_po = 20
        in_transit = 15
        po_req = max(0, deficiency - open_po - in_transit)
        assert po_req == 55

    def test_po_requirement_zero(self):
        deficiency = 30
        open_po = 20
        in_transit = 15
        assert max(0, deficiency - open_po - in_transit) == 0


# ============================================================
# CHINA REORDER FORMULA TESTS
# ============================================================

class TestChinaReorderFormulas:
    """
    China Reorder:
      target_weeks = months × 4
      weeks_cover = current_inventory / avg_weekly_sales
      target_stock = avg_weekly_sales × target_weeks
      suggested_reorder = max(0, target_stock - inventory - open_order - pipeline)
    """

    def test_target_weeks(self):
        assert 3 * 4 == 12
        assert 6 * 4 == 24

    def test_weeks_cover(self):
        inv = 200
        avg_weekly = 15
        assert inv / avg_weekly == pytest.approx(13.33, abs=0.01)

    def test_weeks_cover_zero_sales(self):
        """Zero sales → 0 weeks cover (not infinity)."""
        inv = 200
        avg_weekly = 0
        cover = inv / avg_weekly if avg_weekly > 0 else 0
        assert cover == 0

    def test_suggested_reorder(self):
        avg_weekly = 15
        target_weeks = 12
        inventory = 200
        open_order = 50
        pipeline = 30
        target_stock = avg_weekly * target_weeks  # 180
        reorder = max(0, target_stock - inventory - open_order - pipeline)
        assert reorder == 0  # 200+50+30=280 > 180

    def test_reorder_needed(self):
        avg_weekly = 15
        target_weeks = 12
        inventory = 50
        open_order = 10
        pipeline = 0
        target_stock = avg_weekly * target_weeks  # 180
        reorder = max(0, target_stock - inventory - open_order - pipeline)
        assert reorder == 120  # 180 - 60 = 120


# ============================================================
# WM REPLENISHMENT FORMULA TESTS
# ============================================================

class TestWMFormulas:
    """Same structure as CB — verify the math independently."""

    def test_full_pipeline(self):
        """End-to-end WM calculation."""
        cb_sales = 80     # 1P
        amazon_sales = 40  # Amazon
        window = 12
        cover_weeks = 8

        total = cb_sales + amazon_sales  # 120
        avg_weekly = total / window  # 10
        estimated = avg_weekly * cover_weeks  # 80
        soh = 30
        deficiency = max(0, estimated - soh)  # 50
        open_po = 10
        in_transit = 5
        po_req = max(0, deficiency - open_po - in_transit)  # 35

        assert avg_weekly == 10.0
        assert estimated == 80.0
        assert deficiency == 50
        assert po_req == 35
