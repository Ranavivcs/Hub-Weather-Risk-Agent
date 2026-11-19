"""Shared fixtures: a temporary SQLite database filled with small synthetic data (no network)."""

from datetime import timedelta

import pytest

from app import window as window_mod
from app.db import connect
from app.hubs import HUBS
from app.sources.fema_nri import NRI_FIELDS


@pytest.fixture(autouse=True)
def default_data_window(monkeypatch):
    """Pin DATA_END to the default for every test, so a local .env (e.g. DATA_END=latest) can't change results.

    Tests that need another window set DATA_END themselves with monkeypatch.
    """
    monkeypatch.setenv("DATA_END", window_mod.DEFAULT_END)


@pytest.fixture
def conn(tmp_path):
    """A database where every hub has the full default window (2021-2025); Denver gets snow every 10th day."""
    db = connect(tmp_path / "test.db")
    w = window_mod.target_window()
    days = [w.start + timedelta(days=i) for i in range((w.end - w.start).days + 1)]
    rows = []
    for hub in HUBS:
        for i, d in enumerate(days):
            snow = 2.0 if hub.id == "denver" and i % 10 == 0 else 0.0
            rows.append((hub.id, d.isoformat(), snow, 1.0, 20.0, 25.0, 5.0))
    db.executemany("INSERT INTO weather_daily VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    db.executemany(
        "INSERT INTO nri_county VALUES (?, ?, ?, '2026-01-01')",
        [(hub.county_fips, f, 1.0) for hub in HUBS for f in NRI_FIELDS],
    )
    db.commit()
    yield db
    db.close()


@pytest.fixture
def window(conn):
    """The effective window of the `conn` fixture (the default 2021-2025, fully stored)."""
    return window_mod.effective_window(conn)
