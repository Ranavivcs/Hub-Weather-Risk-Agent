"""The data window (fixed or rolling) and incremental ingest range."""

from datetime import date, timedelta

from app import config, ingest


def test_default_window_is_five_full_years():
    assert (config.DATA_START, config.DATA_END) == ("2021-01-01", "2025-12-31")
    assert config.DATA_YEARS == (2021, 2022, 2023, 2024, 2025)


def test_latest_window_ends_a_week_ago():
    assert config._window_end("latest") == date.today() - timedelta(days=config.ARCHIVE_LAG_DAYS)
    assert config._window_end("2024-06-30") == date(2024, 6, 30)


def test_years_back_handles_leap_day():
    assert config._years_back(date(2024, 2, 29), 5) == date(2019, 2, 28)
    assert config._years_back(date(2025, 12, 31), 5) == date(2020, 12, 31)


def test_missing_range_none_when_complete_and_tail_when_behind(conn):
    assert ingest._missing_range(conn, "denver") is None
    conn.execute("DELETE FROM weather_daily WHERE hub_id = 'denver' AND date > '2025-12-20'")
    assert ingest._missing_range(conn, "denver") == ("2025-12-21", "2025-12-31")


def test_missing_range_full_window_when_start_missing(conn):
    conn.execute("DELETE FROM weather_daily WHERE hub_id = 'denver' AND date < '2021-02-01'")
    assert ingest._missing_range(conn, "denver") == (config.DATA_START, config.DATA_END)
