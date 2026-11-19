"""Shared fixtures: a temporary SQLite database filled with small synthetic data (no network)."""

from datetime import date, timedelta

import pytest

from app import config
from app.db import connect
from app.hubs import HUBS
from app.sources.fema_nri import NRI_FIELDS


@pytest.fixture
def conn(tmp_path, monkeypatch):
    """A database where every hub has the full date window; Denver gets snow every 10th day."""
    db = connect(tmp_path / "test.db")
    start, end = date.fromisoformat(config.DATA_START), date.fromisoformat(config.DATA_END)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
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
