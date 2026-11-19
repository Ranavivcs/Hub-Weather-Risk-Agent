"""The agent loop with a scripted fake Claude client: tool round-trips, validation retry, persistence."""

import json
from types import SimpleNamespace

import pytest
from anthropic.types import TextBlock, ToolUseBlock

from app import agent, conversations


def _final(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(stop_reason="end_turn", content=[TextBlock(type="text", text=json.dumps(payload))])


def _tool_call(name: str, args: dict, call_id: str = "toolu_1") -> SimpleNamespace:
    return SimpleNamespace(stop_reason="tool_use",
                           content=[ToolUseBlock(type="tool_use", id=call_id, name=name, input=args)])


class FakeClient:
    """Returns scripted responses in order and records every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs["messages"])))  # snapshot
        return self.responses.pop(0)


ANSWER = {"status": "answered", "answer": "Denver had snow on some days.", "hub_ids": ["denver"],
          "hazards": ["winter"], "assumptions": [], "uncertainty": []}


def test_tool_round_trip_then_answer(conn):
    cid = conversations.create(conn)
    client = FakeClient([
        _tool_call("weather_stats", {"hub": "denver", "metric": "snow_day", "year": 2025, "threshold": None}),
        _final(ANSWER),
    ])
    result = agent.run_turn(conn, cid, "Snow days in Denver last year?", client=client)

    assert result.answer.hub_ids == ["denver"]
    assert result.tools_used == ["weather_stats"]
    # Scores are attached by code, not by the LLM.
    assert result.hub_scores[0].hub_id == "denver" and result.hub_scores[0].composite_rank >= 1
    # The second request carried the tool result back to the model.
    tool_result = client.requests[1][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["is_error"] is False
    assert json.loads(tool_result["content"])["days_total"] == 365


def test_tool_error_is_returned_to_model_not_raised(conn):
    cid = conversations.create(conn)
    client = FakeClient([_tool_call("hub_breakdown", {"hub": "Boston"}), _final(ANSWER)])
    agent.run_turn(conn, cid, "Why is Boston risky?", client=client)
    tool_result = client.requests[1][-1]["content"][0]
    assert tool_result["is_error"] is True
    assert "Unknown hub" in tool_result["content"]


def test_invalid_answer_gets_one_fix_attempt(conn):
    cid = conversations.create(conn)
    client = FakeClient([_final({**ANSWER, "status": "answered", "answer": "  "}), _final(ANSWER)])
    result = agent.run_turn(conn, cid, "Q", client=client)
    assert result.answer.answer == ANSWER["answer"]
    assert "failed validation" in client.requests[1][-1]["content"][0]["text"]


def test_still_invalid_after_fix_raises_and_stores_nothing(conn):
    cid = conversations.create(conn)
    bad = _final({**ANSWER, "answer": ""})
    with pytest.raises(agent.AgentError):
        agent.run_turn(conn, cid, "Q", client=FakeClient([bad, bad]))
    assert conversations.load_messages(conn, cid) == []


def test_refusal_raises(conn):
    cid = conversations.create(conn)
    refusal = SimpleNamespace(stop_reason="refusal", content=[])
    with pytest.raises(agent.AgentError):
        agent.run_turn(conn, cid, "Q", client=FakeClient([refusal]))


def test_follow_up_sends_previous_turn_as_history(conn):
    cid = conversations.create(conn)
    agent.run_turn(conn, cid, "First question", client=FakeClient([_final(ANSWER)]))
    client = FakeClient([_final(ANSWER)])
    agent.run_turn(conn, cid, "And the follow-up?", client=client)
    sent = client.requests[0]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assert sent[0]["content"][0]["text"] == "First question"
    assert len(conversations.load_messages(conn, cid)) == 4
