"""
Tests for data normalization logic used across services.

Covers:
  - Fossil SKU prefix normalization (FBS/FBO/FBK → FBA)
  - Model name normalization (ETC-07-WH → ETC-07, UB-01 (AI-04...) → UB-01)
  - CB model_join key generation
  - Column normalization patterns
"""
import pytest
import pandas as pd
import re
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestFossilSKUNormalization:
    """
    Fossil shipments use FBS/FBO/FBK prefixes but master uses FBA.
    Pattern: re.sub(r'^FB[^A]', 'FBA', sku)
    """

    @staticmethod
    def normalize_fossil_sku(sku):
        return re.sub(r"^FB[^A]", "FBA", sku)

    def test_fbs_to_fba(self):
        assert self.normalize_fossil_sku("FBS12345") == "FBA12345"

    def test_fbo_to_fba(self):
        assert self.normalize_fossil_sku("FBO99999") == "FBA99999"

    def test_fbk_to_fba(self):
        assert self.normalize_fossil_sku("FBK00001") == "FBA00001"

    def test_fba_unchanged(self):
        assert self.normalize_fossil_sku("FBA66963") == "FBA66963"

    def test_non_fb_prefix_unchanged(self):
        assert self.normalize_fossil_sku("SKU12345") == "SKU12345"

    def test_short_sku(self):
        assert self.normalize_fossil_sku("FB") == "FB"  # too short to match

    def test_empty_string(self):
        assert self.normalize_fossil_sku("") == ""


class TestModelNameNormalization:
    """
    Replicates normalize_model from replenishment.py:
      1. Exact match → keep
      2. Strip after last '-' → check match
      3. Strip after '(' → check match
    """

    @staticmethod
    def normalize_model(m, master_models):
        m = str(m).strip()
        if m in master_models:
            return m
        parts = m.rsplit("-", 1)
        if len(parts) == 2 and parts[0] in master_models:
            return parts[0]
        base = m.split("(")[0].strip()
        if base in master_models:
            return base
        return m

    def test_exact_match(self):
        masters = {"ETC-07", "AM-C1"}
        assert self.normalize_model("ETC-07", masters) == "ETC-07"

    def test_strip_suffix(self):
        """ETC-07-WH → ETC-07 (known from handover bug fixes)."""
        masters = {"ETC-07", "ETC-08"}
        assert self.normalize_model("ETC-07-WH", masters) == "ETC-07"
        assert self.normalize_model("ETC-08-BL", masters) == "ETC-08"

    def test_strip_bundle_description(self):
        """UB-01 (AI-04, AM-S1) → UB-01."""
        masters = {"UB-01", "GB-05"}
        assert self.normalize_model("UB-01 (AI-04, AM-S1, AA-21)", masters) == "UB-01"

    def test_no_match_returns_original(self):
        masters = {"AM-C1"}
        assert self.normalize_model("UNKNOWN-99", masters) == "UNKNOWN-99"

    def test_strip_only_last_dash(self):
        """AM-C11X: rsplit gives ['AM-C11', 'X']. If AM-C11 not in master, try '(' split."""
        masters = {"AM-C11X"}
        # Exact match takes priority
        assert self.normalize_model("AM-C11X", masters) == "AM-C11X"

    def test_whitespace_handling(self):
        masters = {"MOD-A"}
        assert self.normalize_model("  MOD-A  ", masters) == "MOD-A"


class TestModelJoinKey:
    """
    CB Replenishment uses model_join = model.split('(')[0].strip()
    to handle bundle models like "UB-01 (AI-04, AM-S1, AA-21, AM-C2)".
    """

    @staticmethod
    def model_join(model):
        return str(model).split("(")[0].strip()

    def test_simple_model(self):
        assert self.model_join("AM-C1") == "AM-C1"

    def test_bundle_model(self):
        assert self.model_join("UB-01 (AI-04, AM-S1, AA-21, AM-C2)") == "UB-01"

    def test_no_parens(self):
        assert self.model_join("TN-01") == "TN-01"

    def test_empty_parens(self):
        assert self.model_join("GB-05 ()") == "GB-05"

    def test_nested_parens(self):
        assert self.model_join("KB-01 (pack (2))") == "KB-01"


class TestColumnNormalization:
    """All services use df.columns.str.lower().str.strip() pattern."""

    def test_mixed_case_and_spaces(self):
        df = pd.DataFrame(columns=["  Brand ", "MODEL", "Hazmat Type  "])
        df.columns = df.columns.str.lower().str.strip()
        assert list(df.columns) == ["brand", "model", "hazmat type"]

    def test_already_clean(self):
        df = pd.DataFrame(columns=["brand", "model"])
        df.columns = df.columns.str.lower().str.strip()
        assert list(df.columns) == ["brand", "model"]

    def test_preserves_data(self):
        df = pd.DataFrame({"  Price  ": [100]})
        df.columns = df.columns.str.lower().str.strip()
        assert df["price"].iloc[0] == 100


class TestSalesChannelFilter:
    """
    fc_planning normalizes Sales Channel to lowercase before filtering.
    CB filters on channel == '1p Sales' and channel == 'Amazon'.
    """

    def test_case_insensitive_channel_filter(self):
        df = pd.DataFrame({
            "Sales Channel": ["Amazon.in", "AMAZON.IN", "amazon.in", "MCF"],
        })
        df["Sales Channel"] = df["Sales Channel"].str.strip().str.lower()
        amazon = df[df["Sales Channel"] == "amazon.in"]
        assert len(amazon) == 3

    def test_cb_channel_split(self):
        df = pd.DataFrame({
            "channel": ["1p Sales", "Amazon", "B2B", "1p Sales"],
            "units_sold": [10, 20, 5, 15],
        })
        cb = df[df["channel"] == "1p Sales"]["units_sold"].sum()
        cambium = df[df["channel"] == "Amazon"]["units_sold"].sum()
        assert cb == 25
        assert cambium == 20
