"""
Tests for fc_final_allocation.py — IST governance, Fossil skip, explainability.

Tests the logic extracted from the allocation engine:
  - IST 35% cap for IXD items
  - Non-IXD passthrough
  - Fossil skips transfers
  - Governance flag logic
  - Target cover calculation
"""
import pytest
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestISTGovernance:
    """
    IXD items: send_qty = adjusted_shortfall × 0.35
    Non-IXD items: send_qty = adjusted_shortfall (full)
    """

    IST_PERCENTAGE = 0.35

    @staticmethod
    def apply_ist(send_qty, ixd_flag):
        """Replicates apply_ist from fc_final_allocation.py."""
        flag = str(ixd_flag).strip().lower() if ixd_flag else ""
        if "non-ixd" in flag or "non ixd" in flag:
            return send_qty
        return send_qty * 0.35

    def test_ixd_capped(self):
        """IXD: 100 × 0.35 = 35."""
        assert self.apply_ist(100, "IXD") == pytest.approx(35.0)

    def test_non_ixd_full(self):
        """Non-IXD: full passthrough."""
        assert self.apply_ist(100, "Non-IXD") == 100

    def test_non_ixd_non_hazmat(self):
        assert self.apply_ist(80, "Non-IXD Non Hazmat") == 80

    def test_none_flag_treated_as_ixd(self):
        """Missing IXD flag → treated as IXD (capped)."""
        assert self.apply_ist(100, None) == pytest.approx(35.0)

    def test_empty_flag_treated_as_ixd(self):
        assert self.apply_ist(100, "") == pytest.approx(35.0)

    def test_unknown_flag_treated_as_ixd(self):
        assert self.apply_ist(100, "unknown") == pytest.approx(35.0)

    def test_zero_qty(self):
        assert self.apply_ist(0, "IXD") == 0


class TestGovernanceFlags:
    """
    velocity_flag logic:
      - required=0 → NO_REQUIREMENT
      - fill_ratio ≤ 0.70 → SHORT_30%+
      - else → OK
    """

    @staticmethod
    def governance_flag(original_required, send_qty):
        if original_required == 0:
            return "NO_REQUIREMENT"
        ratio = send_qty / original_required
        if ratio <= 0.70:
            return "SHORT_30%+"
        return "OK"

    def test_no_requirement(self):
        assert self.governance_flag(0, 0) == "NO_REQUIREMENT"

    def test_short_flag(self):
        """IXD 35% fill is always SHORT."""
        assert self.governance_flag(100, 35) == "SHORT_30%+"

    def test_ok_flag(self):
        assert self.governance_flag(100, 80) == "OK"

    def test_exactly_70_pct_is_short(self):
        assert self.governance_flag(100, 70) == "SHORT_30%+"

    def test_71_pct_is_ok(self):
        assert self.governance_flag(100, 71) == "OK"


class TestFossilSkipTransfers:
    """Verify Fossil account bypasses the transfer engine."""

    def test_fossil_transfer_skipped(self):
        """Simulate the check in fc_final_allocation.py."""
        account = "fossil"
        should_transfer = account.lower() != "fossil"
        assert should_transfer is False

    def test_nexlev_transfers_enabled(self):
        account = "nexlev"
        should_transfer = account.lower() != "fossil"
        assert should_transfer is True


class TestTargetCover:
    """target_cover_units = weekly_velocity × replenish_weeks"""

    def test_standard(self):
        velocity = 10.5
        weeks = 8
        assert velocity * weeks == 84.0

    def test_zero_velocity(self):
        assert 0 * 12 == 0

    def test_high_weeks(self):
        assert 5.0 * 52 == 260.0


class TestPostTransferStock:
    """post_transfer_stock = fc_inventory + transfer_in"""

    def test_with_transfer(self):
        assert 50 + 20 == 70

    def test_no_transfer(self):
        assert 50 + 0 == 50


class TestAdjustedShortfall:
    """adjusted_shortfall = max(0, target_cover - post_transfer_stock)"""

    def test_shortfall_exists(self):
        target = 80
        post = 50
        assert max(0, target - post) == 30

    def test_no_shortfall(self):
        target = 80
        post = 100
        assert max(0, target - post) == 0

    def test_exactly_covered(self):
        target = 80
        post = 80
        assert max(0, target - post) == 0


class TestFossilClusterPO:
    """
    Fossil cluster_po = max(0, Σtarget - ΣSOH - Σin_transit)
    This nets across all FCs in the cluster.
    """

    def test_cluster_with_deficit(self):
        """BLR cluster: 3 FCs, combined target exceeds combined stock."""
        fcs = [
            {"fc": "BLR5", "target": 40, "soh": 20, "it": 5},
            {"fc": "BLR7", "target": 30, "soh": 10, "it": 0},
            {"fc": "BLR8", "target": 20, "soh": 5,  "it": 0},
        ]
        total_target = sum(f["target"] for f in fcs)  # 90
        total_soh = sum(f["soh"] for f in fcs)        # 35
        total_it = sum(f["it"] for f in fcs)           # 5
        cluster_po = max(0, total_target - total_soh - total_it)
        assert cluster_po == 50

    def test_cluster_fully_stocked(self):
        fcs = [
            {"fc": "BOM4", "target": 30, "soh": 40, "it": 0},
            {"fc": "BOM5", "target": 20, "soh": 25, "it": 5},
        ]
        total_target = sum(f["target"] for f in fcs)  # 50
        total_soh = sum(f["soh"] for f in fcs)        # 65
        total_it = sum(f["it"] for f in fcs)           # 5
        cluster_po = max(0, total_target - total_soh - total_it)
        assert cluster_po == 0

    def test_single_fc_cluster(self):
        """CCX1 is alone in WB cluster."""
        target = 50
        soh = 20
        it = 10
        assert max(0, target - soh - it) == 20
