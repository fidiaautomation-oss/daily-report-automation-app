from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from phase1.google_ads_fetcher import GoogleAdsFetcher, OUTPUT_COLUMNS


def _mock_service(values):
    service = MagicMock()
    service.spreadsheets.return_value.values.return_value.get.return_value.execute.return_value = {
        "values": values
    }
    return service


def test_fetch_filters_target_date():
    fetcher = GoogleAdsFetcher(sheet_id="sid")
    header = OUTPUT_COLUMNS
    rows = [
        ["2026-06-11", "1", "acc", "555", "GC1", "666", "GG1", "200", "10", "2000", "4"],
        ["2026-06-10", "1", "acc", "555", "GC1", "666", "GG1", "100", "5", "1000", "1"],
    ]
    with patch.object(GoogleAdsFetcher, "service", _mock_service([header] + rows)):
        df = fetcher.fetch("2026-06-11")
    assert len(df) == 1
    assert df.iloc[0]["cost"] == "2000"
    assert list(df.columns) == OUTPUT_COLUMNS


def test_fetch_all_rows_when_no_target_date():
    fetcher = GoogleAdsFetcher(sheet_id="sid")
    header = OUTPUT_COLUMNS
    rows = [
        ["2026-06-22", "1", "acc", "555", "GC1", "666", "GG1", "200", "10", "2000", "4"],
        ["2026-06-22", "1", "acc", "555", "GC1", "667", "GG2", "100", "5", "1000", "1"],
    ]
    with patch.object(GoogleAdsFetcher, "service", _mock_service([header] + rows)):
        df = fetcher.fetch()  # 日付指定なし → 全行
    assert len(df) == 2


def test_fetch_empty_sheet_returns_empty():
    fetcher = GoogleAdsFetcher(sheet_id="sid")
    with patch.object(GoogleAdsFetcher, "service", _mock_service([OUTPUT_COLUMNS])):
        df = fetcher.fetch("2026-06-11")
    assert len(df) == 0
    assert list(df.columns) == OUTPUT_COLUMNS


def test_fetch_no_sheet_id_skips():
    fetcher = GoogleAdsFetcher(sheet_id="")
    df = fetcher.fetch("2026-06-11")
    assert len(df) == 0
    assert list(df.columns) == OUTPUT_COLUMNS
