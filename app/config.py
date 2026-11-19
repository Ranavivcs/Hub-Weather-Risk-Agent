"""Runtime settings, read once from environment variables (and `.env` if present)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

# The historical window every frequency metric is computed over (decided with the user: 5 full years).
DATA_START = "2021-01-01"
DATA_END = "2025-12-31"
DATA_YEARS = (2021, 2022, 2023, 2024, 2025)


@dataclass(frozen=True)
class Settings:
    anthropic_model: str
    db_path: Path
    alert_webhook_url: str | None
    chat_limit_per_hour: int  # per client IP, protects the API bill on a public URL


def get_settings() -> Settings:
    """Build settings from the environment. The API key itself is read by the Anthropic SDK, never here."""
    db_path = Path(os.getenv("DB_PATH", "data/weather.db"))
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    return Settings(
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5"),
        db_path=db_path,
        alert_webhook_url=os.getenv("ALERT_WEBHOOK_URL") or None,
        chat_limit_per_hour=int(os.getenv("CHAT_LIMIT_PER_HOUR", "20")),
    )
