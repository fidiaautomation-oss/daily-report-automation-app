from datetime import date, datetime, timedelta, timezone

import pytest

from phase1 import date_range as dr


@pytest.fixture
def fixed_yesterday(monkeypatch):
    fixed = date(2026, 6, 22)
    monkeypatch.setattr(dr, "jst_yesterday", lambda: fixed)
    return fixed


def test_no_args_yesterday_only(fixed_yesterday):
    start, end = dr.parse_date_range([])
    assert start == fixed_yesterday and end == fixed_yesterday


def test_n_days(fixed_yesterday):
    start, end = dr.parse_date_range(["3"])
    assert end == fixed_yesterday
    assert start == date(2026, 6, 20)  # 3日間（20,21,22）


def test_n_days_clamped_to_14(fixed_yesterday):
    start, end = dr.parse_date_range(["30"])
    assert (end - start).days == 13  # 最大14日


def test_single_date(fixed_yesterday):
    start, end = dr.parse_date_range(["2026-06-10"])
    assert start == date(2026, 6, 10) and end == date(2026, 6, 10)


def test_explicit_range(fixed_yesterday):
    start, end = dr.parse_date_range(["2026-06-15", "2026-06-18"])
    assert start == date(2026, 6, 15) and end == date(2026, 6, 18)


def test_range_swapped(fixed_yesterday):
    start, end = dr.parse_date_range(["2026-06-18", "2026-06-15"])
    assert start == date(2026, 6, 15) and end == date(2026, 6, 18)


def test_range_clamped_to_14(fixed_yesterday):
    start, end = dr.parse_date_range(["2026-06-01", "2026-06-30"])
    assert end == date(2026, 6, 30)
    assert (end - start).days == 13


def test_date_list(fixed_yesterday):
    days = dr.date_list(date(2026, 6, 20), date(2026, 6, 22))
    assert days == [date(2026, 6, 20), date(2026, 6, 21), date(2026, 6, 22)]
