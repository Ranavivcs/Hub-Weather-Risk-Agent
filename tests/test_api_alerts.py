"""POST /api/alerts/check: token protection and background run."""

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(monkeypatch, tmp_path):
    runs = []
    monkeypatch.setenv("ALERT_TOKEN", "s3cret")
    monkeypatch.setattr(main, "_run_alert_check", lambda refresh: (runs.append(refresh), main._alert_run_lock.release()))
    c = TestClient(main.app)
    c.runs = runs
    return c


def test_rejects_missing_or_wrong_token(client):
    assert client.post("/api/alerts/check").status_code == 401
    assert client.post("/api/alerts/check", headers={"X-Alert-Token": "nope"}).status_code == 401
    assert client.runs == []


def test_accepts_valid_token_and_runs_in_background(client):
    resp = client.post("/api/alerts/check?refresh=true", headers={"X-Alert-Token": "s3cret"})
    assert resp.status_code == 202
    assert client.runs == [True]


def test_disabled_without_configured_token(client, monkeypatch):
    monkeypatch.delenv("ALERT_TOKEN")
    assert client.post("/api/alerts/check", headers={"X-Alert-Token": "s3cret"}).status_code == 503
