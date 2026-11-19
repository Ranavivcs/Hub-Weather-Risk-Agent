"""Score-change alerts: recompute scores, compare with the last snapshot, notify a webhook.

    python -m app.alerts            # compare current scores with the last snapshot
    python -m app.alerts --refresh  # fetch new data first (useful with DATA_END=latest)

Also triggered by POST /api/alerts/check (see main.py), e.g. daily from an external cron service.
The first run has nothing to compare with, so it only records a baseline.
"""

import argparse
import json
import logging
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import httpx

from app import risk
from app.config import DATA_END, DATA_START, get_settings
from app.db import connect
from app.hubs import find_hub

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScoreChange:
    hub_id: str
    name: str
    previous: float
    current: float
    delta: float
    hazard_deltas: dict[str, float]  # per-hazard change, to show what moved


@dataclass(frozen=True)
class CheckResult:
    computed_at: str
    baseline: bool                   # True on the first run (nothing to compare with)
    changes: list[ScoreChange]
    webhook_status: str              # "sent", "failed: ...", "not configured", "no changes"


def _latest_snapshots(conn: sqlite3.Connection) -> dict[str, dict]:
    """The most recent snapshot per hub: {hub_id: {"composite": ..., "hazards": {...}}}."""
    rows = conn.execute(
        """SELECT s.hub_id, s.composite, s.breakdown_json FROM score_snapshots s
           JOIN (SELECT hub_id, MAX(id) AS id FROM score_snapshots GROUP BY hub_id) latest ON latest.id = s.id"""
    )
    return {r["hub_id"]: {"composite": r["composite"], "hazards": json.loads(r["breakdown_json"])["hazards"]}
            for r in rows}


def find_changes(previous: dict[str, dict], current: dict[str, dict], threshold: float) -> list[ScoreChange]:
    """Hubs whose composite moved by at least `threshold` points. Pure, so it is easy to test."""
    changes = []
    for hub_id, now in current.items():
        before = previous.get(hub_id)
        if before is None:
            continue
        delta = round(now["composite"] - before["composite"], 1)
        if abs(delta) >= threshold:
            hazard_deltas = {h: round(now["hazards"][h] - before["hazards"].get(h, 0.0), 1) for h in now["hazards"]}
            changes.append(ScoreChange(hub_id, find_hub(hub_id).name, before["composite"], now["composite"],
                                       delta, hazard_deltas))
    return sorted(changes, key=lambda c: -abs(c.delta))


def send_webhook(url: str, payload: dict) -> str:
    """POST the alert. Failures are reported, not raised: a broken webhook must not break the check."""
    try:
        resp = httpx.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return "sent"
    except httpx.HTTPError as exc:
        log.warning("alert webhook failed: %s", exc)
        return f"failed: {type(exc).__name__}"


def check_score_changes(conn: sqlite3.Connection, threshold: float, webhook_url: str | None) -> CheckResult:
    """Recompute all scores, store a snapshot, and alert on hubs that moved by >= threshold points."""
    computed_at = datetime.now(UTC).isoformat(timespec="seconds")
    current = {s.hub_id: {"composite": s.composite, "hazards": {h: hs.score for h, hs in s.hazards.items()}}
               for s in risk.score_all(conn)}
    previous = _latest_snapshots(conn)
    changes = find_changes(previous, current, threshold)

    with conn:  # one transaction for the whole snapshot
        conn.executemany(
            "INSERT INTO score_snapshots (hub_id, computed_at, composite, breakdown_json) VALUES (?, ?, ?, ?)",
            [(hub_id, computed_at, v["composite"],
              json.dumps({"hazards": v["hazards"], "window": [DATA_START, DATA_END]}))
             for hub_id, v in current.items()],
        )

    if not changes:
        status = "no changes"
    elif webhook_url is None:
        status = "not configured"
    else:
        status = send_webhook(webhook_url, {
            "event": "hub_risk_score_changed",
            "computed_at": computed_at,
            "threshold": threshold,
            "data_window": [DATA_START, DATA_END],
            "changes": [asdict(c) for c in changes],
        })
    log.info("alert check: baseline=%s changes=%d webhook=%s", not previous, len(changes), status)
    return CheckResult(computed_at, not previous, changes, status)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check hub risk scores for changes and send alerts.")
    parser.add_argument("--refresh", action="store_true", help="fetch new public data first")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    conn = connect(settings.db_path)
    try:
        if args.refresh:
            from app.ingest import refresh
            refresh(conn)
        result = check_score_changes(conn, settings.alert_threshold, settings.alert_webhook_url)
    finally:
        conn.close()
    if result.baseline:
        print("Baseline recorded (first run): nothing to compare with yet.")
    for c in result.changes:
        print(f"{c.name}: {c.previous} -> {c.current} ({c.delta:+})")
    print(f"{len(result.changes)} change(s) >= {settings.alert_threshold} points; webhook: {result.webhook_status}")


if __name__ == "__main__":
    main()
