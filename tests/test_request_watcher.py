from datetime import date
from phase2.request_watcher import _parse_date, _resolve_range


def test_parse_date_slash():
    assert _parse_date("2026/06/22") == date(2026, 6, 22)


def test_parse_date_hyphen():
    assert _parse_date("2026-06-22") == date(2026, 6, 22)


def test_parse_date_invalid():
    assert _parse_date("") is None
    assert _parse_date("---") is None


def test_resolve_range_basic():
    s, e = _resolve_range("2026/06/20", "2026/06/22")
    assert s == date(2026, 6, 20) and e == date(2026, 6, 22)


def test_resolve_range_swapped():
    s, e = _resolve_range("2026/06/22", "2026/06/20")
    assert s == date(2026, 6, 20) and e == date(2026, 6, 22)


def test_resolve_range_clamp_14():
    s, e = _resolve_range("2026/06/01", "2026/06/30")
    assert e == date(2026, 6, 30) and (e - s).days == 13


def test_resolve_range_none():
    assert _resolve_range("", "") == (None, None)
