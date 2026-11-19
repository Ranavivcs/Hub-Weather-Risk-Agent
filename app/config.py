"""Runtime settings from environment variables (and `.env` if present). The data window is in window.py."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")


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
