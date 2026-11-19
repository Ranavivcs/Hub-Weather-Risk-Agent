"""Observed-weather metrics: "% of days where <column> <op> <threshold>", computed in SQL from weather_daily."""

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class WeatherMetric:
    column: str
    op: str  # ">=" or "<="
    default_threshold: float
    unit: str
    description: str


# Whitelist: only these columns/operators ever reach SQL (no user text is interpolated).
WEATHER_METRICS: dict[str, WeatherMetric] = {
    "snowfall_day": WeatherMetric("snowfall_cm", ">=", 0.1, "cm", "days with measurable snowfall"),
    "snow_day": WeatherMetric("snowfall_cm", ">=", 1.0, "cm", "days with at least 1 cm of snow"),
    "deep_freeze_day": WeatherMetric("tmin_c", "<=", -10.0, "°C", "days with a minimum at or below -10 °C"),
    "heavy_rain_day": WeatherMetric("precip_mm", ">=", 50.0, "mm", "days with at least 50 mm of precipitation"),
    "extreme_heat_day": WeatherMetric("tmax_c", ">=", 35.0, "°C", "days with a maximum at or above 35 °C"),
    "strong_gust_day": WeatherMetric("gust_max_kmh", ">=", 60.0, "km/h", "days with wind gusts of at least 60 km/h"),
}


@dataclass(frozen=True)
class MetricResult:
    metric: str
    hub_id: str
    start: str
    end: str
    threshold: float
    days_total: int
    days_matching: int

    @property
    def percent(self) -> float:
        return 100.0 * self.days_matching / self.days_total if self.days_total else 0.0


def day_percentage(
    conn: sqlite3.Connection,
    hub_id: str,
    metric: str,
    start: str,
    end: str,
    threshold: float | None = None,
) -> MetricResult:
    """Count the days in [start, end] where the metric's condition holds. Days with missing values are excluded.

    No default dates on purpose: callers pass the window they computed (see window.py), so nothing is
    frozen at import time.
    """
    spec = WEATHER_METRICS[metric]  # KeyError for unknown metrics, by design
    thr = spec.default_threshold if threshold is None else threshold
    row = conn.execute(
        f"""SELECT COUNT({spec.column}) AS total,
                   COALESCE(SUM({spec.column} {spec.op} ?), 0) AS matching
            FROM weather_daily WHERE hub_id = ? AND date BETWEEN ? AND ?""",
        (thr, hub_id, start, end),
    ).fetchone()
    return MetricResult(metric, hub_id, start, end, thr, row["total"], row["matching"])


def load_nri(conn: sqlite3.Connection, county_fips: str) -> dict[str, float | None]:
    """All stored FEMA NRI fields for a county, as {field: value}."""
    rows = conn.execute("SELECT field, value FROM nri_county WHERE county_fips = ?", (county_fips,))
    return {r["field"]: r["value"] for r in rows}
