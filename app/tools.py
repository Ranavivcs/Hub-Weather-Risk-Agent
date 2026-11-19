"""The tools the LLM can call. Each tool is a JSON schema (sent to Claude) plus a Python handler.

Handlers compute every number with deterministic code; the LLM only chooses which tool to call and
explains the results. Invalid inputs raise ToolError, which goes back to the LLM as an error result.
"""

import sqlite3
from collections.abc import Callable
from typing import Any

from app import risk, scoring
from app.hubs import HUBS, REGIONS, Hub, find_hub
from app.metrics import WEATHER_METRICS, day_percentage
from app.schemas import HubScoreOut
from app.window import Window


class ToolError(ValueError):
    """A tool input the LLM can fix (unknown hub, year out of range, ...)."""


# ---- shared helpers ----

def _resolve_hub(name: str) -> Hub:
    hub = find_hub(name)
    if hub is None:
        raise ToolError(f"Unknown hub {name!r}. Known hubs: {', '.join(h.id for h in HUBS)}")
    return hub


def _ranked(conn: sqlite3.Connection, window: Window, hazard: str | None = None) -> list[scoring.HubScore]:
    return scoring.rank(risk.score_all(conn, window), hazard)


def hub_score_out(score: scoring.HubScore, composite_rank: int) -> HubScoreOut:
    """Compact, API-ready view of one hub's score (also used by the HTTP API)."""
    hub = find_hub(score.hub_id)
    return HubScoreOut(
        hub_id=hub.id,
        name=hub.name,
        state=hub.state,
        region=hub.region,
        composite=score.composite,
        composite_rank=composite_rank,
        hazards={h: s.score for h, s in score.hazards.items()},
        top_drivers=score.top_drivers(),
    )


def scores_by_id(conn: sqlite3.Connection, window: Window) -> dict[str, HubScoreOut]:
    """Every hub's compact score over `window`, keyed by hub id, with its composite rank among all hubs."""
    return {s.hub_id: hub_score_out(s, i + 1) for i, s in enumerate(_ranked(conn, window))}


# ---- handlers (each gets the turn's window from run_tool; list_hubs doesn't need it) ----

def list_hubs(conn: sqlite3.Connection, window: Window, region: str | None) -> dict:
    hubs = [h for h in HUBS if region is None or h.region == region]
    return {"hubs": [{"hub_id": h.id, "name": h.name, "state": h.state, "region": h.region} for h in hubs]}


def rank_hubs(conn: sqlite3.Connection, window: Window, hazard: str, region: str | None, top_n: int | None) -> dict:
    by_hazard = None if hazard == "composite" else hazard
    all_ranked = _ranked(conn, window, by_hazard)
    rows = []
    for position, s in enumerate(all_ranked, start=1):
        hub = find_hub(s.hub_id)
        if region is not None and hub.region != region:
            continue
        value = s.composite if by_hazard is None else s.hazards[by_hazard].score
        rows.append({"rank_among_all_hubs": position, "hub_id": hub.id, "name": hub.name, "region": hub.region,
                     "score": value, "composite": s.composite})
    if top_n is not None:
        rows = rows[: max(1, top_n)]
    return {"ranked_by": hazard, "region": region or "all", "scale": "0-100, higher = more exposed", "hubs": rows}


def hub_breakdown(conn: sqlite3.Connection, window: Window, hub: str) -> dict:
    target = _resolve_hub(hub)
    ranked = _ranked(conn, window)
    position = next(i for i, s in enumerate(ranked, start=1) if s.hub_id == target.id)
    score = ranked[position - 1]
    hazard_ranks = {h: [s.hub_id for s in scoring.rank(ranked, h)].index(target.id) + 1 for h in scoring.HAZARDS}
    return {
        "hub_id": target.id,
        "name": target.name,
        "county": f"{target.county_name} County, {target.state} (FIPS {target.county_fips})",
        "composite": score.composite,
        "composite_rank": f"{position} of {len(ranked)}",
        "top_drivers": score.top_drivers(),
        "hazards": {
            h: {
                "score": hs.score,
                "rank": f"{hazard_ranks[h]} of {len(ranked)}",
                "weight": scoring.HAZARD_WEIGHTS[h],
                "weather_score": hs.weather_score,
                "nri_score": hs.nri_score,
                "inputs": [
                    # Explicit unit: without it the model misread 0.548 (% of days) as 54.8%.
                    {"source": i.source, "what": i.label, "raw": None if i.raw is None else round(i.raw, 2),
                     "unit": "percent of days" if i.source == "weather" else "events per year",
                     "cap": i.cap, "score": round(i.score, 1)}
                    for i in hs.inputs
                ],
            }
            for h, hs in score.hazards.items()
        },
    }


def compare_hubs(conn: sqlite3.Connection, window: Window, hubs: list[str]) -> dict:
    if not 2 <= len(hubs) <= 5:
        raise ToolError("compare_hubs needs between 2 and 5 hubs")
    return {"hubs": [hub_breakdown(conn, window, h) for h in hubs]}


def weather_stats(
    conn: sqlite3.Connection, window: Window, hub: str, metric: str, year: int | None, threshold: float | None
) -> dict:
    target = _resolve_hub(hub)
    if metric not in WEATHER_METRICS:
        raise ToolError(f"Unknown metric {metric!r}. Known: {', '.join(WEATHER_METRICS)}")
    if year is not None and year not in window.years:
        raise ToolError(f"No data for {year}. Available years: {window.years[0]}-{window.years[-1]}")
    start, end = (f"{year}-01-01", f"{year}-12-31") if year else (window.start_iso, window.end_iso)
    result = day_percentage(conn, target.id, metric, start, end, threshold)
    spec = WEATHER_METRICS[metric]
    return {
        "hub_id": target.id,
        "metric": metric,
        "definition": f"{spec.description}; counted as {spec.column} {spec.op} {result.threshold} {spec.unit}",
        "period": f"{start} to {end}",
        "days_total": result.days_total,
        "days_matching": result.days_matching,
        "percent": round(result.percent, 1),
        "source": "Open-Meteo Historical (ERA5-based reanalysis, ~25 km grid) at the hub's city-center coordinates",
    }


# ---- schemas sent to Claude (strict: arguments always match the schema) ----

# Nullable enum: strict schemas need anyOf here (a type list combined with an enum is rejected by the API).
_NULLABLE_REGION = {"anyOf": [{"type": "string", "enum": list(REGIONS)}, {"type": "null"}],
                    "description": "US Census region, or null for all"}
_HUB = {"type": "string", "description": "Hub id or city name, e.g. 'dallas' or 'St. Louis'"}


def _tool(name: str, description: str, properties: dict) -> dict:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {"type": "object", "properties": properties,
                         "required": list(properties), "additionalProperties": False},
    }


TOOL_SCHEMAS: list[dict] = [
    _tool("list_hubs", "List the hubs in the network, optionally for one region.", {"region": _NULLABLE_REGION}),
    _tool(
        "rank_hubs",
        "Rank hubs by the composite risk score or by one hazard's score (0-100, higher = more exposed).",
        {
            "hazard": {"type": "string", "enum": ["composite", *scoring.HAZARDS]},
            "region": _NULLABLE_REGION,
            "top_n": {"type": ["integer", "null"], "description": "Return only the first N hubs, or null for all"},
        },
    ),
    _tool(
        "hub_breakdown",
        "Full score breakdown for one hub: composite, per-hazard scores and ranks, and every raw input "
        "(observed weather % of days, FEMA events/yr) with its cap. Use this to explain WHY a score is high or low.",
        {"hub": _HUB},
    ),
    _tool("compare_hubs", "Side-by-side breakdowns for 2-5 hubs.",
          {"hubs": {"type": "array", "items": _HUB, "description": "2 to 5 hubs"}}),
    _tool(
        "weather_stats",
        # The years are in the system prompt (they move with the data); the tool list stays fixed.
        "Percentage of days meeting a weather condition at a hub, for one year or the whole "
        "5-year data window. Metrics: "
        + "; ".join(f"{name} = {m.description} (default {m.column} {m.op} {m.default_threshold} {m.unit})"
                    for name, m in WEATHER_METRICS.items()),
        {
            "hub": _HUB,
            "metric": {"type": "string", "enum": list(WEATHER_METRICS)},
            "year": {"type": ["integer", "null"], "description": "Calendar year, or null for the whole window"},
            "threshold": {"type": ["number", "null"], "description": "Override the default threshold, or null"},
        },
    ),
]

_HANDLERS: dict[str, Callable[..., dict]] = {
    "list_hubs": list_hubs,
    "rank_hubs": rank_hubs,
    "hub_breakdown": hub_breakdown,
    "compare_hubs": compare_hubs,
    "weather_stats": weather_stats,
}


def run_tool(conn: sqlite3.Connection, name: str, args: dict[str, Any], window: Window) -> dict:
    """Execute one tool call over the caller's data window. Raises ToolError for unknown tools or bad arguments.

    The window is required so every tool in a chat turn uses the same window as the system prompt.
    """
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ToolError(f"Unknown tool {name!r}")
    try:
        return handler(conn, window, **args)
    except TypeError as exc:  # wrong/missing argument names
        raise ToolError(f"Bad arguments for {name}: {exc}") from exc
