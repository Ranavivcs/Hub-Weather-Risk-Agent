"""Pydantic models: the JSON contract between the LLM and our code, and the HTTP API shapes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.hubs import HUBS
from app.scoring import HAZARDS

HubId = Literal[tuple(h.id for h in HUBS)]
Hazard = Literal[HAZARDS]


class AgentAnswer(BaseModel):
    """The structured final answer the LLM must return (enforced via the API's JSON-schema output).

    The LLM only names hubs; the scores shown next to the answer are attached by our code from the
    scoring module, so no number in `hub_scores` can come from the LLM.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["answered", "out_of_scope", "needs_clarification"] = Field(
        description="out_of_scope: the question is about a hub, hazard or period we have no data for."
    )
    answer: str = Field(description="The answer for the analyst, with the reasoning. Plain text; '- ' bullets allowed.")
    bottom_line: str = Field(description=(
        "One plain-language sentence (at most 30 words) that sums up the answer for someone skimming the "
        "conversation later. It must agree with the answer; name the hub(s) and the key number if there is one."
    ))
    hub_ids: list[HubId] = Field(description="Hubs the answer is about, most exposed first. Empty if none.")
    hazards: list[Hazard] = Field(description="Hazards the answer is about. Empty if the composite score.")
    assumptions: list[str] = Field(description="Assumptions this answer relies on.")
    uncertainty: list[str] = Field(description="Data limitations and caveats that affect this answer.")


def answer_json_schema() -> dict:
    """JSON schema sent to the Messages API as `output_config.format`."""
    return AgentAnswer.model_json_schema()


# ---- HTTP API ----

class ChatRequest(BaseModel):
    conversation_id: str | None = Field(default=None, description="Omit to start a new conversation.")
    message: str = Field(min_length=1, max_length=2000)


class HubScoreOut(BaseModel):
    hub_id: str
    name: str
    state: str
    region: str
    composite: float
    composite_rank: int = Field(description="1 = most exposed of all hubs")
    hazards: dict[str, float]
    top_drivers: list[str]


class ChatResponse(BaseModel):
    conversation_id: str
    answer: AgentAnswer
    hub_scores: list[HubScoreOut] = Field(description="Deterministic scores for answer.hub_ids, attached by code.")
    tools_used: list[str]
