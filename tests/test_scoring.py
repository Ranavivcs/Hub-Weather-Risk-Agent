"""Unit tests for the deterministic scoring (no network, no database)."""

import pytest

from app import scoring

# A hub with every input exactly at half its cap -> every input scores 50.
HALF_WEATHER = {i.key: i.cap / 2 for specs in scoring.WEATHER_INPUTS.values() for i in specs}
HALF_NRI = {i.key: i.cap / 2 for specs in scoring.NRI_INPUTS.values() for i in specs}


@pytest.mark.parametrize(
    ("raw", "cap", "expected"),
    [(0, 10, 0.0), (5, 10, 50.0), (10, 10, 100.0), (25, 10, 100.0), (None, 10, 0.0), (-3, 10, 0.0)],
)
def test_normalize_maps_to_0_100_and_caps(raw, cap, expected):
    assert scoring.normalize(raw, cap) == expected


def test_normalize_rejects_bad_cap():
    with pytest.raises(ValueError):
        scoring.normalize(1, 0)


def test_weights_cover_every_hazard_and_sum_to_one():
    assert set(scoring.HAZARD_WEIGHTS) == set(scoring.HAZARDS)
    assert sum(scoring.HAZARD_WEIGHTS.values()) == pytest.approx(1.0)


def test_every_hazard_has_nri_inputs():
    # A hazard with no inputs at all would divide by zero.
    assert all(scoring.NRI_INPUTS[h] for h in scoring.HAZARDS)


def test_hazard_blends_weather_and_nri_half_and_half():
    weather = {"snow_day": 10.0, "deep_freeze_day": 15.0}             # both at cap -> weather 100
    nri = {"WNTW_AFREQ": 0.0, "ISTM_AFREQ": 0.0, "CWAV_AFREQ": 0.0}   # NRI 0
    result = scoring.score_hazard("winter", weather, nri)
    assert result.weather_score == 100.0
    assert result.nri_score == 0.0
    assert result.score == 50.0


def test_hurricane_uses_nri_only():
    result = scoring.score_hazard("hurricane", {}, {"HRCN_AFREQ": 0.15})
    assert result.weather_score is None
    assert result.score == 50.0


def test_missing_nri_value_counts_as_zero():
    # Inland county: FEMA has no coastal-flood value (None).
    nri = {"IFLD_AFREQ": 6.0, "CFLD_AFREQ": None}
    result = scoring.score_hazard("flood", {"heavy_rain_day": 0.0}, nri)
    assert result.nri_score == 50.0   # mean(100, 0)
    assert result.score == 25.0


def test_composite_is_weighted_mean_of_hazards():
    hub = scoring.score_hub("x", HALF_WEATHER, HALF_NRI)
    assert all(h.score == 50.0 for h in hub.hazards.values())
    assert hub.composite == 50.0


def test_score_depends_only_on_own_data():
    # Fixed caps: adding a much worse hub must not change another hub's score.
    a = scoring.score_hub("a", HALF_WEATHER, HALF_NRI)
    worse = scoring.score_hub("b", {k: v * 4 for k, v in HALF_WEATHER.items()}, {k: v * 4 for k, v in HALF_NRI.items()})
    ranked = scoring.rank([a, worse])
    assert [s.hub_id for s in ranked] == ["b", "a"]
    assert ranked[1].composite == a.composite == 50.0


def test_rank_by_single_hazard_and_tie_break():
    hot = scoring.score_hub("hot", {**HALF_WEATHER, "extreme_heat_day": 30.0}, HALF_NRI)
    base1 = scoring.score_hub("b1", HALF_WEATHER, HALF_NRI)
    base2 = scoring.score_hub("a1", HALF_WEATHER, HALF_NRI)
    assert [s.hub_id for s in scoring.rank([base1, hot, base2], hazard="heat")] == ["hot", "a1", "b1"]


def test_rank_rejects_unknown_hazard():
    with pytest.raises(ValueError):
        scoring.rank([], hazard="earthquake")


def test_top_drivers_orders_by_contribution():
    hub = scoring.score_hub("x", {**HALF_WEATHER, "extreme_heat_day": 30.0}, {**HALF_NRI, "HRCN_AFREQ": 0.0})
    drivers = hub.top_drivers(5)
    assert drivers[0] == "heat"
    assert drivers[-1] == "hurricane"
