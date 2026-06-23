from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from phase1.google_ads_fetcher import GoogleAdsFetcher, OUTPUT_COLUMNS


def _row(date, acc, camp, adg, cost):
    return [date, acc, "acc", camp, "C", adg, "G", "10", "1", cost, "0"]


def _mock_service(tabs: dict):
    """tabs: {タブ名: [行,...]}（ヘッダー除く）。google_ads_* タブを模す。"""
    service = MagicMock()
    ss = service.spreadsheets.return_value

    ss.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"title": t}} for t in tabs]
    }

    def values_get(spreadsheetId, range):
        tab = range.split("'")[1]
        rows = tabs.get(tab, [])
        return MagicMock(execute=MagicMock(return_value={
            "values": [OUTPUT_COLUMNS] + rows if rows else [OUTPUT_COLUMNS]
        }))

    ss.values.return_value.get.side_effect = values_get
    return service


def test_fetch_merges_tabs_and_dedupes():
    fetcher = GoogleAdsFetcher(sheet_id="sid")
    tabs = {
        "google_ads_111": [
            _row("2026-06-22", "A", "1", "10", "100"),
            _row("2026-06-22", "A", "1", "11", "200"),
        ],
        # MCC重複: account A の同一行が別MCCにも出る
        "google_ads_222": [
            _row("2026-06-22", "A", "1", "10", "100"),
            _row("2026-06-22", "B", "2", "20", "300"),
        ],
    }
    with patch.object(GoogleAdsFetcher, "service", _mock_service(tabs)):
        df = fetcher.fetch()
    # 重複(A/1/10)が1件に → 3行
    assert len(df) == 3
    keys = set(zip(df["account_id"], df["campaign_id"], df["adgroup_id"]))
    assert keys == {("A", "1", "10"), ("A", "1", "11"), ("B", "2", "20")}


def test_fetch_filters_target_date():
    fetcher = GoogleAdsFetcher(sheet_id="sid")
    tabs = {
        "google_ads_111": [
            _row("2026-06-22", "A", "1", "10", "100"),
            _row("2026-06-21", "A", "1", "10", "100"),
        ],
    }
    with patch.object(GoogleAdsFetcher, "service", _mock_service(tabs)):
        df = fetcher.fetch("2026-06-22")
    assert len(df) == 1
    assert df.iloc[0]["date"] == "2026-06-22"


def test_fetch_no_tabs_returns_empty():
    fetcher = GoogleAdsFetcher(sheet_id="sid")
    with patch.object(GoogleAdsFetcher, "service", _mock_service({})):
        df = fetcher.fetch()
    assert len(df) == 0
    assert list(df.columns) == OUTPUT_COLUMNS


def test_fetch_no_sheet_id_skips():
    fetcher = GoogleAdsFetcher(sheet_id="")
    df = fetcher.fetch("2026-06-21")
    assert len(df) == 0
    assert list(df.columns) == OUTPUT_COLUMNS
