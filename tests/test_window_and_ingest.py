"""The data window (target vs effective) and incremental ingest.

Covers the two issues from the external review:
  1. The window must be computed at call time, so a long-running server rolls forward (DATA_END=latest).
  2. Scores must never use a partly empty window (e.g. after a restart, data only to the image build).
"""

from datetime import date, timedelta

import pytest

from app import ingest, risk
from app.window import (
    ARCHIVE_LAG_DAYS,
    DataNotLoadedError,
    Window,
    _years_back,
    effective_window,
    target_window,
    window_ending,
)

FIXED = Window(date(2021, 1, 1), date(2025, 12, 31))


# ---- target window ----

def test_default_target_is_five_full_years():
    assert target_window() == FIXED            # DATA_END pinned to the default by conftest
    assert FIXED.years == (2021, 2022, 2023, 2024, 2025)


def test_latest_target_is_computed_per_call(monkeypatch):
    """Regression for issue 1: two calls on different days give different windows (nothing frozen at import)."""
    monkeypatch.setenv("DATA_END", "latest")
    day1, day2 = date(2026, 11, 19), date(2026, 11, 20)
    assert target_window(day1).end == day1 - timedelta(days=ARCHIVE_LAG_DAYS)
    assert target_window(day2).end == target_window(day1).end + timedelta(days=1)


def test_years_back_handles_leap_day():
    assert _years_back(date(2024, 2, 29), 5) == date(2019, 2, 28)
    assert window_ending(date(2025, 12, 31)) == FIXED


def test_years_are_only_full_calendar_years():
    assert window_ending(date(2026, 11, 12)).years == (2022, 2023, 2024, 2025)


# ---- effective window ----

def test_fixed_end_with_complete_data_equals_target(conn):
    assert effective_window(conn) == target_window() == FIXED


def test_one_lagging_hub_caps_the_window_for_every_hub(conn):
    conn.execute("DELETE FROM weather_daily WHERE hub_id = 'denver' AND date > '2025-12-20'")
    w = effective_window(conn)
    assert w.end == date(2025, 12, 20)
    assert w.start == date(2020, 12, 21)       # still a full 5 years, ending at the lagging hub's last day


def test_hub_with_no_data_raises_data_not_loaded(conn):
    conn.execute("DELETE FROM weather_daily WHERE hub_id = 'denver'")
    with pytest.raises(DataNotLoadedError, match="denver"):
        effective_window(conn)


def test_empty_database_raises_data_not_loaded(conn):
    conn.execute("DELETE FROM weather_daily")
    with pytest.raises(DataNotLoadedError):
        effective_window(conn)


def test_restart_scores_use_the_full_stored_window(conn, monkeypatch):
    """Regression for issue 2: latest target, data only to 2025 -> scores use exactly 2021-2025."""
    fixed_scores = risk.score_all(conn, effective_window(conn))
    monkeypatch.setenv("DATA_END", "latest")
    today = date(2026, 11, 19)
    assert target_window(today).end > FIXED.end   # the target already reaches into 2026...
    w = effective_window(conn, today)
    assert w == FIXED                              # ...but scores only use data that exists
    assert risk.score_all(conn, w) == fixed_scores


# ---- incremental ingest ----

def test_missing_range_none_when_complete_and_tail_when_behind(conn):
    assert ingest._missing_range(conn, "denver", FIXED) is None
    conn.execute("DELETE FROM weather_daily WHERE hub_id = 'denver' AND date > '2025-12-20'")
    assert ingest._missing_range(conn, "denver", FIXED) == ("2025-12-21", "2025-12-31")


def test_missing_range_full_window_when_start_missing(conn):
    conn.execute("DELETE FROM weather_daily WHERE hub_id = 'denver' AND date < '2021-02-01'")
    assert ingest._missing_range(conn, "denver", FIXED) == ("2021-01-01", "2025-12-31")


def test_daily_refresh_keeps_rolling_forward(conn, monkeypatch):
    """Regression for issue 1: refreshes on consecutive days each fetch the new day, and the window follows."""
    monkeypatch.setenv("DATA_END", "latest")
    fetched = []

    def fake_fetch(lat, lon, start, end):
        fetched.append((start, end))
        d, last, rows = date.fromisoformat(start), date.fromisoformat(end), []
        while d <= last:
            rows.append({"date": d.isoformat(), "snowfall_cm": 0.0, "precip_mm": 1.0,
                         "gust_max_kmh": 20.0, "tmax_c": 25.0, "tmin_c": 5.0})
            d += timedelta(days=1)
        return rows

    monkeypatch.setattr(ingest.open_meteo, "fetch_daily", fake_fetch)
    day1 = date(2026, 1, 1) + timedelta(days=ARCHIVE_LAG_DAYS)   # target end = 2026-01-01
    ingest.ingest_weather(conn, today=day1)
    ingest.ingest_weather(conn, today=day1 + timedelta(days=1))  # next day: target end = 2026-01-02

    assert set(fetched[:15]) == {("2026-01-01", "2026-01-01")}   # one new day per hub
    assert set(fetched[15:]) == {("2026-01-02", "2026-01-02")}   # and the next day, the day after
    assert effective_window(conn, day1 + timedelta(days=1)).end == date(2026, 1, 2)
