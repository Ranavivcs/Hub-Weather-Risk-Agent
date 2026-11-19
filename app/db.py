"""SQLite storage: one file, created on first use. Plain `sqlite3`, no ORM, so every query is visible."""

import sqlite3
from pathlib import Path

SCHEMA = """
-- One row per hub per day, from Open-Meteo Historical (ERA5-based reanalysis).
CREATE TABLE IF NOT EXISTS weather_daily (
    hub_id        TEXT NOT NULL,
    date          TEXT NOT NULL,          -- ISO date, local time of the hub
    snowfall_cm   REAL,
    precip_mm     REAL,
    gust_max_kmh  REAL,
    tmax_c        REAL,
    tmin_c        REAL,
    PRIMARY KEY (hub_id, date)
);

-- FEMA National Risk Index values per county; one row per field (e.g. HAIL_AFREQ).
CREATE TABLE IF NOT EXISTS nri_county (
    county_fips   TEXT NOT NULL,
    field         TEXT NOT NULL,
    value         REAL,                    -- NULL when FEMA has no value (hazard not applicable)
    fetched_at    TEXT NOT NULL,
    PRIMARY KEY (county_fips, field)
);

-- History of computed scores, used to detect changes for alerts.
CREATE TABLE IF NOT EXISTS score_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    hub_id          TEXT NOT NULL,
    computed_at     TEXT NOT NULL,
    composite       REAL NOT NULL,
    breakdown_json  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,           -- uuid4 hex
    created_at  TEXT NOT NULL
);

-- Full Claude message history, append-only. content_json holds the exact content blocks
-- (text, tool_use, tool_result, thinking) because they must be sent back unchanged.
CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id),
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content_json     TEXT NOT NULL,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database (creating the file and tables if needed). Rows come back as dict-like `Row`s."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
