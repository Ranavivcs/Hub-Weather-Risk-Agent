"""The JSON contract with the LLM, and tool input validation."""

import json

import pytest
from pydantic import ValidationError

from app import tools
from app.schemas import AgentAnswer, answer_json_schema

VALID = {"status": "answered", "answer": "Houston.", "hub_ids": ["houston"], "hazards": ["flood"],
         "assumptions": [], "uncertainty": []}


def test_valid_answer_parses():
    assert AgentAnswer.model_validate_json(json.dumps(VALID)).hub_ids == ["houston"]


@pytest.mark.parametrize(
    "change",
    [
        {"hub_ids": ["boston"]},          # hub not in the network
        {"hazards": ["earthquake"]},      # hazard we do not model
        {"status": "maybe"},              # not an allowed status
        {"extra_field": 1},               # no undeclared fields
    ],
)
def test_invalid_answers_are_rejected(change):
    with pytest.raises(ValidationError):
        AgentAnswer.model_validate_json(json.dumps({**VALID, **change}))


def test_missing_required_field_is_rejected():
    without = {k: v for k, v in VALID.items() if k != "uncertainty"}
    with pytest.raises(ValidationError):
        AgentAnswer.model_validate_json(json.dumps(without))


def test_json_schema_is_closed_and_requires_everything():
    schema = answer_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(AgentAnswer.model_fields)


def test_tool_schemas_are_strict_and_complete():
    for tool in tools.TOOL_SCHEMAS:
        s = tool["input_schema"]
        assert tool["strict"] is True
        assert s["additionalProperties"] is False
        assert set(s["required"]) == set(s["properties"]), tool["name"]


def test_weather_stats_counts_days(conn):
    # Synthetic data: Denver has 2 cm of snow on every 10th day counted from 2021-01-01. 2024 spans
    # day indexes 1095..1460 (leap year, 366 days); multiples of 10 in that range: 1100..1460 -> 37 days.
    out = tools.run_tool(conn, "weather_stats", {"hub": "Denver", "metric": "snow_day", "year": 2024, "threshold": None})
    assert out["days_total"] == 366
    assert out["days_matching"] == 37
    assert out["percent"] == 10.1


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("weather_stats", {"hub": "Boston", "metric": "snow_day", "year": None, "threshold": None}),
        ("weather_stats", {"hub": "denver", "metric": "snow_day", "year": 2019, "threshold": None}),
        ("weather_stats", {"hub": "denver", "metric": "fog_day", "year": None, "threshold": None}),
        ("compare_hubs", {"hubs": ["dallas"]}),
        ("hub_breakdown", {"hub_name": "dallas"}),   # wrong argument name
        ("delete_everything", {}),
    ],
)
def test_bad_tool_inputs_raise_tool_error(conn, name, args):
    with pytest.raises(tools.ToolError):
        tools.run_tool(conn, name, args)


def test_rank_hubs_filters_region_and_keeps_global_rank(conn):
    out = tools.run_tool(conn, "rank_hubs", {"hazard": "winter", "region": "West", "top_n": None})
    assert {h["region"] for h in out["hubs"]} == {"West"}
    assert out["hubs"][0]["hub_id"] == "denver"            # the only hub with snow in the synthetic data
    assert out["hubs"][0]["rank_among_all_hubs"] == 1
