"""Deterministic hazard scoring. Pure functions: raw inputs in, scores out. No database, no network, no LLM.

How a score is built:
  1. Each raw input is mapped to 0-100 with a fixed cap: min(value / cap, 1) * 100.
     Caps sit near the high end of large US cities, so 100 means "about as bad as a major US hub gets".
     Fixed caps (instead of ranking hubs against each other) keep a hub's score dependent only on its own
     data, so a score change means that hub's data changed.
  2. Hazard score = 50% observed weather (Open-Meteo, mean of its inputs)
                  + 50% FEMA NRI annual event frequency (mean of its inputs).
     A hazard with no observed-weather input (hurricane) uses NRI only.
  3. Composite = weighted mean of the hazard scores (equal weights, decided with the user).
"""

from dataclasses import dataclass, field

HAZARDS = ("winter", "hurricane", "flood", "heat", "severe_storm")

HAZARD_WEIGHTS: dict[str, float] = {h: 0.2 for h in HAZARDS}

WEATHER_SHARE = 0.5  # share of a hazard score that comes from observed weather, when available


@dataclass(frozen=True)
class Input:
    key: str     # metric name (weather) or FEMA field (NRI)
    cap: float   # raw value that maps to 100
    label: str


# Observed-weather inputs: % of days in the 5-year window (see metrics.WEATHER_METRICS).
WEATHER_INPUTS: dict[str, tuple[Input, ...]] = {
    "winter": (
        Input("snow_day", 10.0, "% days with >=1 cm snow"),
        Input("deep_freeze_day", 15.0, "% days with min <= -10 °C"),
    ),
    # Reanalysis weather (~25 km grid) does not resolve hurricane winds, so no observed input here.
    "hurricane": (),
    "flood": (Input("heavy_rain_day", 1.5, "% days with >=50 mm precipitation"),),
    "heat": (Input("extreme_heat_day", 30.0, "% days with max >= 35 °C"),),
    "severe_storm": (Input("strong_gust_day", 8.0, "% days with gusts >= 60 km/h"),),
}

# FEMA National Risk Index inputs: expected events per year (AFREQ) for the hub's county.
NRI_INPUTS: dict[str, tuple[Input, ...]] = {
    "winter": (
        Input("WNTW_AFREQ", 15.0, "winter weather events/yr"),
        Input("ISTM_AFREQ", 1.5, "ice storm events/yr"),
        Input("CWAV_AFREQ", 8.0, "cold wave events/yr"),
    ),
    "hurricane": (Input("HRCN_AFREQ", 0.3, "hurricane events/yr"),),
    "flood": (
        Input("IFLD_AFREQ", 6.0, "riverine flood events/yr"),
        Input("CFLD_AFREQ", 4.0, "coastal flood events/yr"),
    ),
    "heat": (Input("HWAV_AFREQ", 20.0, "heat wave events/yr"),),
    "severe_storm": (
        Input("TRND_AFREQ", 1.5, "tornado events/yr"),
        Input("HAIL_AFREQ", 10.0, "hail events/yr"),
        Input("SWND_AFREQ", 6.0, "strong wind events/yr"),
    ),
}


@dataclass(frozen=True)
class InputScore:
    source: str              # "weather" | "nri"
    key: str
    label: str
    raw: float | None        # None = FEMA has no value for this county (treated as 0)
    cap: float
    score: float             # 0-100


@dataclass(frozen=True)
class HazardScore:
    hazard: str
    score: float
    weather_score: float | None   # None when the hazard has no observed-weather input
    nri_score: float
    inputs: tuple[InputScore, ...]


@dataclass(frozen=True)
class HubScore:
    hub_id: str
    composite: float
    hazards: dict[str, HazardScore] = field(default_factory=dict)

    def top_drivers(self, n: int = 2) -> list[str]:
        """The hazards that contribute most to the composite, highest first."""
        return sorted(self.hazards, key=lambda h: HAZARD_WEIGHTS[h] * self.hazards[h].score, reverse=True)[:n]


def normalize(raw: float | None, cap: float) -> float:
    """Map a raw value to 0-100 against a cap. Missing (None) and negative values count as 0."""
    if cap <= 0:
        raise ValueError(f"cap must be positive, got {cap}")
    if raw is None or raw <= 0:
        return 0.0
    return min(raw / cap, 1.0) * 100.0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _score_inputs(source: str, specs: tuple[Input, ...], raw: dict[str, float | None]) -> list[InputScore]:
    return [InputScore(source, s.key, s.label, raw.get(s.key), s.cap, normalize(raw.get(s.key), s.cap)) for s in specs]


def score_hazard(hazard: str, weather_raw: dict[str, float], nri_raw: dict[str, float | None]) -> HazardScore:
    """Score one hazard from raw weather percentages and raw NRI frequencies."""
    weather = _score_inputs("weather", WEATHER_INPUTS[hazard], weather_raw)
    nri = _score_inputs("nri", NRI_INPUTS[hazard], nri_raw)
    nri_score = _mean([i.score for i in nri])
    if weather:
        weather_score = _mean([i.score for i in weather])
        score = WEATHER_SHARE * weather_score + (1 - WEATHER_SHARE) * nri_score
    else:
        weather_score, score = None, nri_score
    return HazardScore(hazard, round(score, 1), _round(weather_score), round(nri_score, 1), tuple(weather + nri))


def score_hub(hub_id: str, weather_raw: dict[str, float], nri_raw: dict[str, float | None]) -> HubScore:
    """Score every hazard and the weighted composite for one hub."""
    hazards = {h: score_hazard(h, weather_raw, nri_raw) for h in HAZARDS}
    composite = sum(HAZARD_WEIGHTS[h] * hazards[h].score for h in HAZARDS)
    return HubScore(hub_id, round(composite, 1), hazards)


def rank(scores: list[HubScore], hazard: str | None = None) -> list[HubScore]:
    """Sort hubs by composite (or by one hazard's score), highest exposure first. Ties break by hub id."""
    if hazard is not None and hazard not in HAZARDS:
        raise ValueError(f"unknown hazard {hazard!r}; expected one of {HAZARDS}")

    def key(s: HubScore) -> tuple[float, str]:
        value = s.composite if hazard is None else s.hazards[hazard].score
        return (-value, s.hub_id)

    return sorted(scores, key=key)


def required_weather_metrics() -> set[str]:
    """Names of the weather metrics the scoring needs (so the caller knows what to compute)."""
    return {i.key for specs in WEATHER_INPUTS.values() for i in specs}


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)
