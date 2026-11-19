"""Load public data into SQLite. Run once (or to refresh): `python -m app.ingest`.

Idempotent: rows are upserted, so re-running replaces values instead of duplicating them.
"""

import argparse
import logging
from datetime import date, datetime, timezone

from app.config import DATA_END, DATA_START, get_settings
from app.db import connect
from app.hubs import HUBS
from app.sources import fema_nri, open_meteo

log = logging.getLogger(__name__)


EXPECTED_DAYS = (date.fromisoformat(DATA_END) - date.fromisoformat(DATA_START)).days + 1


def ingest_weather(conn, force: bool = False) -> None:
    """Fetch the full daily window for every hub (one Open-Meteo call per hub).

    Hubs that already have the whole window stored are skipped unless `force`, so an interrupted
    run (e.g. after a rate limit) can simply be re-run.
    """
    for hub in HUBS:
        stored = conn.execute(
            "SELECT COUNT(*) FROM weather_daily WHERE hub_id = ? AND date BETWEEN ? AND ?",
            (hub.id, DATA_START, DATA_END),
        ).fetchone()[0]
        if stored == EXPECTED_DAYS and not force:
            log.info("weather: %s already complete, skipping", hub.id)
            continue
        rows = open_meteo.fetch_daily(hub.lat, hub.lon, DATA_START, DATA_END)
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
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.executemany(
        "INSERT OR REPLACE INTO nri_county (county_fips, field, value, fetched_at) VALUES (?, ?, ?, ?)",
        [(fips, field, value, fetched_at) for fips, fields in counties.items() for field, value in fields.items()],
    )
    conn.commit()
    log.info("nri: %d counties", len(counties))


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Open-Meteo and FEMA NRI data into SQLite.")
    parser.add_argument("--force", action="store_true", help="re-download weather even if already stored")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    conn = connect(get_settings().db_path)
    ingest_nri(conn)
    ingest_weather(conn, force=args.force)
    conn.close()


if __name__ == "__main__":
    main()
