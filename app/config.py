"""Runtime settings, read once from environment variables (and `.env` if present)."""

import os
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

YEARS_OF_HISTORY = 5           # decided with the user
ARCHIVE_LAG_DAYS = 7           # Open-Meteo's archive trails real time by a few days


def _window_end(value: str) -> date:
    """DATA_END env: an ISO date, or "latest" for a rolling window ending about a week ago."""
    return date.today() - timedelta(days=ARCHIVE_LAG_DAYS) if value == "latest" else date.fromisoformat(value)


def _years_back(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # Feb 29 in a non-leap target year
        return d.replace(year=d.year - years, day=28)


# The historical window every frequency metric is computed over. Default: the fixed 5 full years
# 2021-2025. DATA_END=latest makes it roll forward, so scores (and alerts) follow new weather.
_END = _window_end(os.getenv("DATA_END", "2025-12-31"))
_START = _years_back(_END, YEARS_OF_HISTORY) + timedelta(days=1)
DATA_START = _START.isoformat()
DATA_END = _END.isoformat()
# Calendar years fully inside the window (what "per year" questions can be answered for).
DATA_YEARS = tuple(y for y in range(_START.year, _END.year + 1) if date(y, 1, 1) >= _START and date(y, 12, 31) <= _END)


@dataclass(frozen=True)
class Settings:
    anthropic_model: str
    db_path: Path
    alert_webhook_url: str | None
    alert_threshold: float     # composite-score change (points) that triggers an alert
    alert_token: str | None    # shared secret for POST /api/alerts/check; unset = endpoint disabled
    chat_limit_per_hour: int   # per client IP, protects the API bill on a public URL


def get_settings() -> Settings:
    """Build settings from the environment. The API key itself is read by the Anthropic SDK, never here."""
    db_path = Path(os.getenv("DB_PATH", "data/weather.db"))
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    return Settings(
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        db_path=db_path,
        alert_webhook_url=os.getenv("ALERT_WEBHOOK_URL") or None,
        alert_threshold=float(os.getenv("ALERT_THRESHOLD", "1.0")),
        alert_token=os.getenv("ALERT_TOKEN") or None,
        chat_limit_per_hour=int(os.getenv("CHAT_LIMIT_PER_HOUR", "20")),
    )
