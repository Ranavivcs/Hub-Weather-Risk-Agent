"""The historical data window: which dates every frequency metric is computed over.

Two windows, both computed when called (never frozen at import, so a long-running server rolls forward):

- target_window(): what we *want* to cover. DATA_END env = an ISO date (default 2025-12-31, the fixed
  5 full years 2021-2025) or "latest" (5 years ending about a week ago). Only ingest uses it, to decide
  what to download.
- effective_window(conn): what everything the user sees uses: scores, the "last year" in the agent's
  prompt, weather_stats years and periods, alert snapshots. It ends at the earlier of the target end and
  the last day stored for *every* hub, and spans 5 full years before that, so scores never use a partly
  empty window (e.g. after a restart, when the database only holds the data baked into the image).

Callers compute the effective window once per unit of work (a chat turn, an API request, an alert check)
and pass it down, so a refresh finishing mid-turn cannot give the prompt and the tools different windows.
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from app.hubs import HUBS

YEARS_OF_HISTORY = 5   # decided with the user
ARCHIVE_LAG_DAYS = 7   # Open-Meteo's archive trails real time by a few days
DEFAULT_END = "2025-12-31"


class DataNotLoadedError(RuntimeError):
    """Raised when the database lacks data for a hub (run `python -m app.ingest`)."""


@dataclass(frozen=True)
class Window:
    start: date
    end: date

    @property
    def start_iso(self) -> str:
        return self.start.isoformat()

    @property
    def end_iso(self) -> str:
        return self.end.isoformat()

    @property
    def years(self) -> tuple[int, ...]:
        """Calendar years fully inside the window (what "per year" questions can be answered for)."""
        return tuple(y for y in range(self.start.year, self.end.year + 1)
                     if date(y, 1, 1) >= self.start and date(y, 12, 31) <= self.end)


def _years_back(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # Feb 29 in a non-leap target year
        return d.replace(year=d.year - years, day=28)


def window_ending(end: date) -> Window:
    """The YEARS_OF_HISTORY-year window that ends on `end` (inclusive)."""
    return Window(_years_back(end, YEARS_OF_HISTORY) + timedelta(days=1), end)


def target_end(value: str, today: date) -> date:
    """Parse DATA_END: an ISO date, or "latest" for about a week before `today`."""
    return today - timedelta(days=ARCHIVE_LAG_DAYS) if value == "latest" else date.fromisoformat(value)


def target_window(today: date | None = None) -> Window:
    """The window we want data for, read from DATA_END now (not at import)."""
    return window_ending(target_end(os.getenv("DATA_END", DEFAULT_END), today or date.today()))


def effective_window(conn: sqlite3.Connection, today: date | None = None) -> Window:
    """The window scores and answers use: the target, but never past the data stored for every hub.

    Raises DataNotLoadedError if any hub has no weather data at all.
    """
    last_by_hub = dict(conn.execute("SELECT hub_id, MAX(date) FROM weather_daily GROUP BY hub_id").fetchall())
    missing = [h.id for h in HUBS if last_by_hub.get(h.id) is None]
    if missing:
        raise DataNotLoadedError(f"no weather data for {', '.join(missing)}; run `python -m app.ingest`")
    last_common = min(date.fromisoformat(last_by_hub[h.id]) for h in HUBS)
    return window_ending(min(target_window(today).end, last_common))
