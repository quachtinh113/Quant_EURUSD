from datetime import datetime, timezone

from server.time_engine import TimeEngine


def test_entry_windows_01_03_and_31_33_vn() -> None:
    te = TimeEngine(7, 15)
    dt_in = datetime(2026, 3, 1, 0, 2, tzinfo=timezone.utc)  # 07:02 VN
    dt_out = datetime(2026, 3, 1, 0, 10, tzinfo=timezone.utc)  # 07:10 VN
    dt_in2 = datetime(2026, 3, 1, 0, 31, tzinfo=timezone.utc)  # 07:31 VN

    assert te.in_entry_window(dt_in).in_window is True
    assert te.in_entry_window(dt_out).in_window is False
    assert te.in_entry_window(dt_in2).in_window is True


def test_asia_session_vn_07_00_to_15_00() -> None:
    te = TimeEngine(7, 15)
    before = datetime(2026, 3, 1, 23, 30, tzinfo=timezone.utc)  # 06:30 VN
    inside = datetime(2026, 3, 1, 1, 0, tzinfo=timezone.utc)  # 08:00 VN
    at_end = datetime(2026, 3, 1, 8, 0, tzinfo=timezone.utc)  # 15:00 VN

    assert te.in_session(before) is False
    assert te.in_session(inside) is True
    assert te.in_session(at_end) is False
