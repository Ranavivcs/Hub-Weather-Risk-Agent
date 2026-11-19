"""Client for the Open-Meteo Historical Weather API (free, no key): https://open-meteo.com/en/docs/historical-weather-api"""

import time

import httpx

MAX_ATTEMPTS = 4
RETRY_WAIT_S = 30
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = ("snowfall_sum", "precipitation_sum", "wind_gusts_10m_max", "temperature_2m_max", "temperature_2m_min")


def fetch_daily(lat: float, lon: float, start: str, end: str) -> list[dict]:
    """Fetch daily weather for one point. Returns rows with our column names (metric units)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": ",".join(DAILY_VARS),
        "timezone": "auto",
    }
    for attempt in range(MAX_ATTEMPTS):
        resp = httpx.get(ARCHIVE_URL, params=params, timeout=60)
        if resp.status_code != 429 or attempt == MAX_ATTEMPTS - 1:
            break
        # Free tier rate limit (multi-year requests count as several calls): back off and retry.
        time.sleep(RETRY_WAIT_S * (attempt + 1))
    resp.raise_for_status()
    daily = resp.json()["daily"]
    return [
        {
            "date": day,
            "snowfall_cm": daily["snowfall_sum"][i],
            "precip_mm": daily["precipitation_sum"][i],
            "gust_max_kmh": daily["wind_gusts_10m_max"][i],
            "tmax_c": daily["temperature_2m_max"][i],
            "tmin_c": daily["temperature_2m_min"][i],
        }
        for i, day in enumerate(daily["time"])
    ]
