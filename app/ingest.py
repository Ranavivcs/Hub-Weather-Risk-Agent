"""Load public data into SQLite. Run once (or to refresh): `python -m app.ingest`.

Idempotent: rows are upserted, so re-running replaces values instead of duplicating them.
"""

import argparse
import logging
from datetime import UTC, date, datetime, timedelta

from app.config import DATA_END, DATA_START, get_settings
from app.db import connect
from app.hubs import HUBS
from app.sources import fema_nri, open_meteo

log = logging.getLogger(__name__)


def _missing_range(conn, hub_id: str) -> tuple[str, str] | None:
    """The date range still to fetch for a hub, or None if the window is fully stored.

    Only the tail is fetched when the window has moved forward (DATA_END=latest), so a daily refresh
    is one small call per hub. A gap at the start (window moved back) refetches the whole window.
    """
    first, last = conn.execute(
        "SELECT MIN(date), MAX(date) FROM weather_daily WHERE hub_id = ? AND date BETWEEN ? AND ?",
        (hub_id, DATA_START, DATA_END),
    ).fetchone()
    if first is None or first > DATA_START:
        return DATA_START, DATA_END
    if last < DATA_END:
        return (date.fromisoformat(last) + timedelta(days=1)).isoformat(), DATA_END
    return None


def ingest_weather(conn, force: bool = False) -> None:
    """Fetch the missing days of the window for every hub (at most one Open-Meteo call per hub).

    Already-stored days are skipped unless `force`, so an interrupted run (e.g. after a rate limit)
    can simply be re-run, and a daily refresh only fetches the new days.
    """
    for hub in HUBS:
        span = (DATA_START, DATA_END) if force else _missing_range(conn, hub.id)
        if span is None:
            log.info("weather: %s up to date, skipping", hub.id)
            continue
        rows = open_meteo.fetch_daily(hub.lat, hub.lon, *span)
        conn.executemany(
            """INSERT OR REPLACE INTO weather_daily
               (hub_id, date, snowfall_cm, precip_mm, gust_max_kmh, tmax_c, tmin_c)
               VALUES (:hub_id, :date, :snowfall_cm, :precip_mm, :gust_max_kmh, :tmax_c, :tmin_c)""",
            [{"hub_id": hub.id, **row} for row in rows],
        )
        conn.commit()
        log.info("weather: %s -> %d days", hub.id, len(rows))


def ingest_nri(conn) -> None:
    """Fetch FEMA NRI values for all hub counties in a single query."""
    counties = fema_nri.fetch_counties([hub.county_fips for hub in HUBS])
    missing = {hub.county_fips for hub in HUBS} - counties.keys()
    if missing:
        raise RuntimeError(f"FEMA NRI returned no data for counties {sorted(missing)}")
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    conn.executemany(
        "INSERT OR REPLACE INTO nri_county (county_fips, field, value, fetched_at) VALUES (?, ?, ?, ?)",
        [(fips, field, value, fetched_at) for fips, fields in counties.items() for field, value in fields.items()],
    )
    conn.commit()
    log.info("nri: %d counties", len(counties))


def refresh(conn, force: bool = False) -> None:
    """Bring the database up to date with both public sources."""
    ingest_nri(conn)
    ingest_weather(conn, force=force)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Open-Meteo and FEMA NRI data into SQLite.")
    parser.add_argument("--force", action="store_true", help="re-download weather even if already stored")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    conn = connect(get_settings().db_path)
    log.info("window: %s to %s", DATA_START, DATA_END)
    refresh(conn, force=args.force)
    conn.close()


if __name__ == "__main__":
    main()
