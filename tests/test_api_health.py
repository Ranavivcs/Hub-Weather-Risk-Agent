"""GET /api/health reports the window scores use; /api/hubs returns 503 when a hub has no data."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.db import connect


@pytest.fixture
def client(conn):
    """Serve the test database through FastAPI's dependency override (the real DB is never opened).

    Like the real app, each request opens its own connection (FastAPI runs it in a worker thread).
    """
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]

    def test_conn():
        c = connect(Path(db_file))
        try:
            yield c
        finally:
            c.close()

    main.app.dependency_overrides[main.get_conn] = test_conn
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_health_shows_effective_window_and_target(client, monkeypatch):
    monkeypatch.setenv("DATA_END", "latest")
    body = client.get("/api/health").json()
    assert body["data_loaded"] is True
    assert body["data_window"]["start"] == "2021-01-01" and body["data_window"]["end"] == "2025-12-31"
    assert body["data_window"]["full_years"] == [2021, 2022, 2023, 2024, 2025]
    assert body["target_end"] > "2025-12-31"     # the target is ahead until a refresh catches up


def test_hub_without_data_gives_503_not_a_crash(client, conn):
    conn.execute("DELETE FROM weather_daily WHERE hub_id = 'denver'")
    conn.commit()  # the request uses its own connection
    resp = client.get("/api/hubs")
    assert resp.status_code == 503 and "denver" in resp.json()["detail"]
    assert client.get("/api/health").json()["data_loaded"] is False
