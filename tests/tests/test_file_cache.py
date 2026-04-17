"""
Tests for file_cache.py — caching layer for CSV/Excel data.

Uses tmp files to avoid depending on real data files.
"""
import pytest
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch
from app.services.file_cache import _cache, get, get_excel_sheet, invalidate


@pytest.fixture(autouse=True)
def clear_cache():
    """Start each test with a clean cache."""
    _cache.clear()
    yield
    _cache.clear()


class TestCacheGet:

    @patch("app.services.file_cache.pd.read_csv")
    def test_csv_loaded_and_cached(self, mock_read):
        mock_read.return_value = pd.DataFrame({"a": [1, 2, 3]})
        result = get("test.csv")
        assert len(result) == 3
        assert "test.csv" in _cache
        # Second call should not re-read
        get("test.csv")
        assert mock_read.call_count == 1

    @patch("app.services.file_cache.pd.read_excel")
    def test_excel_loaded(self, mock_read):
        mock_read.return_value = pd.DataFrame({"x": [10]})
        result = get("test.xlsx")
        assert result["x"].iloc[0] == 10
        assert "test.xlsx" in _cache

    @patch("app.services.file_cache.pd.read_csv")
    def test_returns_copy(self, mock_read):
        """Modifying returned DF should not corrupt cache."""
        mock_read.return_value = pd.DataFrame({"a": [1, 2, 3]})
        df1 = get("copy_test.csv")
        df1["a"] = 999  # Mutate
        df2 = get("copy_test.csv")
        assert list(df2["a"]) == [1, 2, 3]  # Cache untouched


class TestCacheExcelSheet:

    @patch("app.services.file_cache.pd.read_excel")
    def test_sheet_loading(self, mock_read):
        mock_read.return_value = pd.DataFrame({"col": ["val"]})
        result = get_excel_sheet("book.xlsx", "Sheet1")
        assert len(result) == 1
        assert "book.xlsx::Sheet1" in _cache

    @patch("app.services.file_cache.pd.read_excel")
    def test_different_sheets_cached_separately(self, mock_read):
        mock_read.side_effect = [
            pd.DataFrame({"sheet": ["AA"]}),
            pd.DataFrame({"sheet": ["WM"]}),
        ]
        r1 = get_excel_sheet("master.xlsx", "AA")
        r2 = get_excel_sheet("master.xlsx", "WM")
        assert r1["sheet"].iloc[0] == "AA"
        assert r2["sheet"].iloc[0] == "WM"
        assert "master.xlsx::AA" in _cache
        assert "master.xlsx::WM" in _cache


class TestCacheInvalidation:

    @patch("app.services.file_cache.pd.read_csv")
    def test_invalidate_specific(self, mock_read):
        mock_read.return_value = pd.DataFrame({"a": [1]})
        get("file1.csv")
        get("file2.csv")
        assert len(_cache) == 2

        invalidate("file1.csv")
        assert "file1.csv" not in _cache
        assert "file2.csv" in _cache

    @patch("app.services.file_cache.pd.read_csv")
    def test_invalidate_all(self, mock_read):
        mock_read.return_value = pd.DataFrame({"a": [1]})
        get("a.csv")
        get("b.csv")
        invalidate()
        assert len(_cache) == 0

    @patch("app.services.file_cache.pd.read_excel")
    def test_invalidate_prefix_catches_sheets(self, mock_read):
        """invalidate('master.xlsx') should clear master.xlsx::Sheet1 too."""
        mock_read.return_value = pd.DataFrame({"x": [1]})
        get_excel_sheet("master.xlsx", "Sheet1")
        get_excel_sheet("master.xlsx", "Sheet2")
        assert len(_cache) == 2

        invalidate("master.xlsx")
        assert len(_cache) == 0
