"""Glue between storage and the pure scoring module: read raw inputs from SQLite, return scores."""

import sqlite3

from app import scoring
from app.hubs import HUBS, Hub
from app.metrics import day_percentage, load_nri
from app.window import DataNotLoadedError, Window

__all__ = ["DataNotLoadedError", "hub_raw_inputs", "score_all"]


def hub_raw_inputs(
    conn: sqlite3.Connection, hub: Hub, window: Window
) -> tuple[dict[str, float], dict[str, float | None]]:
    """Raw inputs for one hub over `window`: ({weather metric: % of days}, {NRI field: events/yr})."""
    weather = {}
    for metric in scoring.required_weather_metrics():
        result = day_percentage(conn, hub.id, metric, window.start_iso, window.end_iso)
        if result.days_total == 0:
            raise DataNotLoadedError(f"no weather data for {hub.id}; run `python -m app.ingest`")
        weather[metric] = result.percent
    nri = load_nri(conn, hub.county_fips)
    if not nri:
        raise DataNotLoadedError(f"no FEMA NRI data for county {hub.county_fips}; run `python -m app.ingest`")
    return weather, nri


def score_all(conn: sqlite3.Connection, window: Window) -> list[scoring.HubScore]:
    """Scores for every hub over `window`, in hub-list order. Cheap (15 hubs x a few SQL aggregates).

    The window is required: the caller computes effective_window() once per unit of work and passes it.
    """
    return [scoring.score_hub(hub.id, *hub_raw_inputs(conn, hub, window)) for hub in HUBS]
