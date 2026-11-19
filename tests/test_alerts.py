"""Score-change alerts: baseline, threshold, webhook payload, and webhook failure handling."""

import httpx
import pytest

from app import alerts


def _hub(composite, **hazards):
    return {"composite": composite, "hazards": {"winter": 10.0, "heat": 10.0, **hazards}}


def test_find_changes_respects_threshold_and_sorts_by_size():
    previous = {"dallas": _hub(40.0), "miami": _hub(40.0), "denver": _hub(20.0)}
    current = {"dallas": _hub(43.0, heat=25.0), "miami": _hub(40.5), "denver": _hub(14.0)}
    changes = alerts.find_changes(previous, current, threshold=1.0)
    assert [c.hub_id for c in changes] == ["denver", "dallas"]     # miami moved only 0.5
    assert changes[1].delta == 3.0 and changes[1].hazard_deltas["heat"] == 15.0


def test_new_hub_without_previous_snapshot_is_not_an_alert():
    assert alerts.find_changes({}, {"dallas": _hub(40.0)}, threshold=1.0) == []


@pytest.fixture
def webhook(monkeypatch):
    """Capture webhook POSTs instead of sending them."""
    sent = []

    def fake_post(url, json, timeout):
        sent.append((url, json))
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(alerts.httpx, "post", fake_post)
    return sent


def test_first_run_is_baseline_then_change_triggers_webhook(conn, webhook):
    first = alerts.check_score_changes(conn, threshold=1.0, webhook_url="https://hooks.example/x")
    assert first.baseline and first.changes == [] and webhook == []

    # Dallas County's hail frequency jumps -> its severe-storm and composite scores rise.
    conn.execute("UPDATE nri_county SET value = 9.0 WHERE county_fips = '48113' AND field = 'HAIL_AFREQ'")
    second = alerts.check_score_changes(conn, threshold=1.0, webhook_url="https://hooks.example/x")

    assert not second.baseline
    assert [c.hub_id for c in second.changes] == ["dallas"]
    assert second.webhook_status == "sent"
    _url, payload = webhook[0]
    assert payload["event"] == "hub_risk_score_changed"
    assert payload["changes"][0]["hub_id"] == "dallas"
    assert payload["changes"][0]["hazard_deltas"]["severe_storm"] > 0


def test_no_change_sends_nothing(conn, webhook):
    alerts.check_score_changes(conn, threshold=1.0, webhook_url="https://hooks.example/x")
    result = alerts.check_score_changes(conn, threshold=1.0, webhook_url="https://hooks.example/x")
    assert result.changes == [] and result.webhook_status == "no changes" and webhook == []


def test_webhook_failure_is_reported_not_raised(conn, monkeypatch):
    def failing_post(url, json, timeout):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(alerts.httpx, "post", failing_post)
    alerts.check_score_changes(conn, threshold=1.0, webhook_url="https://hooks.example/x")
    conn.execute("UPDATE nri_county SET value = 9.0 WHERE county_fips = '48113' AND field = 'HAIL_AFREQ'")
    result = alerts.check_score_changes(conn, threshold=1.0, webhook_url="https://hooks.example/x")
    assert result.webhook_status.startswith("failed")
    # The snapshot is still stored, so the next run compares against the new scores, not the old ones.
    latest = alerts._latest_snapshots(conn)["dallas"]["composite"]
    assert latest == result.changes[0].current
    assert conn.execute("SELECT COUNT(*) FROM score_snapshots").fetchone()[0] == 2 * 15


def test_snapshot_stores_the_effective_window(conn, monkeypatch):
    import json as _json
    monkeypatch.setenv("DATA_END", "latest")   # target reaches past the stored data (ends 2025-12-31)
    alerts.check_score_changes(conn, threshold=1.0, webhook_url=None)
    stored = _json.loads(conn.execute("SELECT breakdown_json FROM score_snapshots LIMIT 1").fetchone()[0])
    assert stored["window"] == ["2021-01-01", "2025-12-31"]
