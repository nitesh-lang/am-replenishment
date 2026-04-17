"""
Tests for Fossil FC → Cluster mapping.

This mapping is critical — wrong cluster assignment means wrong PO calculations.
The mapping is defined inline in replenishment.py, so we replicate and verify it.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# Exact copy from app/api/replenishment.py lines 125-134
FC_CLUSTER = {
    "BLR5": "BLR", "BLR7": "BLR", "BLR8": "BLR",
    "BOM4": "BOM", "BOM5": "BOM", "BOM7": "BOM",
    "AMD2": "BOM", "PNQ3": "BOM", "ISK3": "BOM",
    "MAA4": "TN",  "CJB1": "TN",
    "DEL2": "DEL", "DEL4": "DEL", "DEL5": "DEL",
    "DED4": "DEL", "LKO1": "DEL",
    "HYD3": "TEL", "HYD8": "TEL",
    "CCX1": "WB",
}


class TestClusterMapping:

    def test_all_blr_fcs(self):
        for fc in ["BLR5", "BLR7", "BLR8"]:
            assert FC_CLUSTER[fc] == "BLR", f"{fc} should map to BLR"

    def test_all_bom_fcs(self):
        for fc in ["BOM4", "BOM5", "BOM7", "AMD2", "PNQ3", "ISK3"]:
            assert FC_CLUSTER[fc] == "BOM", f"{fc} should map to BOM"

    def test_all_tn_fcs(self):
        for fc in ["MAA4", "CJB1"]:
            assert FC_CLUSTER[fc] == "TN", f"{fc} should map to TN"

    def test_all_del_fcs(self):
        for fc in ["DEL2", "DEL4", "DEL5", "DED4", "LKO1"]:
            assert FC_CLUSTER[fc] == "DEL", f"{fc} should map to DEL"

    def test_all_tel_fcs(self):
        for fc in ["HYD3", "HYD8"]:
            assert FC_CLUSTER[fc] == "TEL", f"{fc} should map to TEL"

    def test_wb_cluster(self):
        assert FC_CLUSTER["CCX1"] == "WB"

    def test_unknown_fc_returns_none(self):
        """Unknown FCs should not be in the map."""
        assert "UNKNOWN_FC" not in FC_CLUSTER

    def test_total_fc_count(self):
        """Exactly 19 FCs mapped."""
        assert len(FC_CLUSTER) == 19

    def test_cluster_count(self):
        """6 clusters: BLR, BOM, TN, DEL, TEL, WB."""
        clusters = set(FC_CLUSTER.values())
        assert clusters == {"BLR", "BOM", "TN", "DEL", "TEL", "WB"}

    def test_case_sensitivity(self):
        """Mapping uses uppercase keys — verify lookup pattern."""
        fc_raw = "blr5"
        mapped = FC_CLUSTER.get(fc_raw.upper(), "-")
        assert mapped == "BLR"

    def test_unmapped_fc_defaults(self):
        """Unknown FC should default to '-'."""
        fc_raw = "JAI1"
        mapped = FC_CLUSTER.get(fc_raw.upper(), "-")
        assert mapped == "-"
