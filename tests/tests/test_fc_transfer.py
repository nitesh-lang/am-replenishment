"""
Tests for fc_transfer.py — inter-FC transfer logic.

These test the transfer algorithm in isolation using synthetic FC plan data.
"""
import pytest
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestFCTransferAlgorithm:
    """
    Test the transfer logic without calling calculate_fc_transfers
    (which depends on file I/O). Instead, replicate the algorithm.
    """

    @staticmethod
    def run_transfer_logic(df: pd.DataFrame) -> pd.DataFrame:
        """
        Replicates the exact algorithm from fc_transfer.py
        so we can test it against synthetic DataFrames.
        """
        df = df.copy()
        df["excess"] = (df["fc_inventory"] - df["required_units"]).clip(lower=0)
        transfers = []

        for sku in df["sku"].unique():
            sku_df = df[df["sku"] == sku].copy()
            shortage_fcs = sku_df[sku_df["fc_shortfall"] > 0].sort_values("fc_shortfall", ascending=False)
            excess_fcs = sku_df[sku_df["excess"] > 0].sort_values("excess", ascending=False)

            for s_idx, short_row in shortage_fcs.iterrows():
                remaining_shortage = short_row["fc_shortfall"]
                for e_idx, excess_row in excess_fcs.iterrows():
                    if remaining_shortage <= 0:
                        break
                    available_excess = df.loc[e_idx, "excess"]
                    transfer_qty = min(available_excess, remaining_shortage)
                    if transfer_qty > 0:
                        transfers.append({
                            "sku": sku,
                            "from_fc": excess_row["fulfillment_center"],
                            "to_fc": short_row["fulfillment_center"],
                            "transfer_qty": int(round(transfer_qty, 0)),
                        })
                        df.loc[e_idx, "excess"] -= transfer_qty
                        remaining_shortage -= transfer_qty

        return pd.DataFrame(transfers)

    def test_simple_transfer(self):
        """FC1 has excess, FC2 has shortage → transfer happens."""
        df = pd.DataFrame([
            {"sku": "SKU-A", "fulfillment_center": "FC1",
             "fc_inventory": 100, "required_units": 50, "fc_shortfall": 0},
            {"sku": "SKU-A", "fulfillment_center": "FC2",
             "fc_inventory": 10, "required_units": 80, "fc_shortfall": 70},
        ])
        result = self.run_transfer_logic(df)
        assert len(result) == 1
        assert result.iloc[0]["from_fc"] == "FC1"
        assert result.iloc[0]["to_fc"] == "FC2"
        assert result.iloc[0]["transfer_qty"] == 50  # min(excess=50, shortage=70)

    def test_no_transfer_when_balanced(self):
        """Both FCs are adequately stocked → no transfers."""
        df = pd.DataFrame([
            {"sku": "SKU-A", "fulfillment_center": "FC1",
             "fc_inventory": 80, "required_units": 80, "fc_shortfall": 0},
            {"sku": "SKU-A", "fulfillment_center": "FC2",
             "fc_inventory": 40, "required_units": 40, "fc_shortfall": 0},
        ])
        result = self.run_transfer_logic(df)
        assert len(result) == 0

    def test_partial_fill(self):
        """Excess at FC1 can only partially cover FC2's shortage."""
        df = pd.DataFrame([
            {"sku": "SKU-A", "fulfillment_center": "FC1",
             "fc_inventory": 60, "required_units": 50, "fc_shortfall": 0},  # excess=10
            {"sku": "SKU-A", "fulfillment_center": "FC2",
             "fc_inventory": 0, "required_units": 80, "fc_shortfall": 80},
        ])
        result = self.run_transfer_logic(df)
        assert len(result) == 1
        assert result.iloc[0]["transfer_qty"] == 10

    def test_multi_source_transfer(self):
        """FC2 shortage filled by both FC1 and FC3."""
        df = pd.DataFrame([
            {"sku": "SKU-A", "fulfillment_center": "FC1",
             "fc_inventory": 70, "required_units": 50, "fc_shortfall": 0},  # excess=20
            {"sku": "SKU-A", "fulfillment_center": "FC2",
             "fc_inventory": 0, "required_units": 50, "fc_shortfall": 50},
            {"sku": "SKU-A", "fulfillment_center": "FC3",
             "fc_inventory": 90, "required_units": 50, "fc_shortfall": 0},  # excess=40
        ])
        result = self.run_transfer_logic(df)
        total_transferred = result["transfer_qty"].sum()
        assert total_transferred == 50  # Fully covers shortage
        assert set(result["from_fc"]) <= {"FC1", "FC3"}

    def test_cross_sku_isolation(self):
        """Excess in SKU-A cannot fill shortage in SKU-B."""
        df = pd.DataFrame([
            {"sku": "SKU-A", "fulfillment_center": "FC1",
             "fc_inventory": 200, "required_units": 50, "fc_shortfall": 0},  # excess=150
            {"sku": "SKU-B", "fulfillment_center": "FC1",
             "fc_inventory": 0, "required_units": 100, "fc_shortfall": 100},
        ])
        result = self.run_transfer_logic(df)
        # SKU-A has excess but SKU-B at same FC has shortage — no cross-SKU transfer
        assert len(result) == 0

    def test_all_shortage_no_excess(self):
        """Every FC is short → no transfers possible."""
        df = pd.DataFrame([
            {"sku": "SKU-A", "fulfillment_center": "FC1",
             "fc_inventory": 10, "required_units": 50, "fc_shortfall": 40},
            {"sku": "SKU-A", "fulfillment_center": "FC2",
             "fc_inventory": 5, "required_units": 80, "fc_shortfall": 75},
        ])
        result = self.run_transfer_logic(df)
        assert len(result) == 0

    def test_zero_shortfall_zero_excess(self):
        """Both exactly at target → no action."""
        df = pd.DataFrame([
            {"sku": "SKU-A", "fulfillment_center": "FC1",
             "fc_inventory": 50, "required_units": 50, "fc_shortfall": 0},
        ])
        result = self.run_transfer_logic(df)
        assert len(result) == 0
