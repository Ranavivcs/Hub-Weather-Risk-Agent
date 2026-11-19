"""The agent loop: Claude picks tools, our code runs them, and the final answer is schema-validated JSON.

One user message = one "turn":
  1. Send history + new message, with the tool schemas and the AgentAnswer JSON schema (output_config.format).
  2. While Claude asks for tools (stop_reason == "tool_use"): run them, send the results back.
  3. Parse the final text as AgentAnswer (Pydantic). If our extra checks fail, ask Claude once to fix it.
  4. Store the whole turn, attach deterministic scores for the hubs named, return.
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import date

import anthropic
from pydantic import ValidationError

from app import conversations, scoring
from app.config import get_settings
from app.hubs import HUBS
from app.schemas import AgentAnswer, HubScoreOut, answer_json_schema
from app.tools import TOOL_SCHEMAS, ToolError, run_tool, scores_by_id
from app.window import Window, effective_window

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8       # guard against a runaway tool loop
MAX_FIX_ATTEMPTS = 1      # re-asks when the final answer fails validation
MAX_BOTTOM_LINE_WORDS = 40  # schema asks for <= 30; a little slack before forcing a retry
MAX_TOKENS = 16000
EFFORT = "medium"


class AgentError(RuntimeError):
    """The turn could not produce a valid answer (refusal, truncation, loop limit, invalid output)."""


@dataclass
class TurnResult:
    conversation_id: str
    answer: AgentAnswer
    hub_scores: list[HubScoreOut]
    tools_used: list[str]


def _methodology() -> str:
    """Scoring rules for the prompt, generated from scoring.py so the two can't drift apart."""
    lines = []
    for h in scoring.HAZARDS:
        weather = ", ".join(f"{i.label} (cap {i.cap})" for i in scoring.WEATHER_INPUTS[h]) or "none (FEMA only)"
        nri = ", ".join(f"{i.label} (cap {i.cap})" for i in scoring.NRI_INPUTS[h])
        lines.append(f"- {h} (weight {scoring.HAZARD_WEIGHTS[h]:.0%}): observed weather: {weather}; FEMA NRI: {nri}")
    return "\n".join(lines)


def system_prompt(today: date, window: Window) -> str:
    """The system prompt for one turn. `window` is the turn's effective window (the one the tools use)."""
    hubs = "; ".join(f"{h.id} = {h.name}, {h.state} ({h.region})" for h in HUBS)
    return f"""You are a weather-risk analyst assistant for a US logistics company. Analysts use you to decide which \
distribution hubs are most exposed to weather disruption and should get resilience investment.

Hub network (assumed; the company gave no list): {hubs}.

Data:
- Observed weather: Open-Meteo Historical (ERA5-based reanalysis, ~25 km grid) at each hub's city center, daily, \
{window.start_iso} to {window.end_iso}. Full years available: {window.years[0]}-{window.years[-1]}. "Last year" \
means {window.years[-1]}, the latest full year in the data.
- FEMA National Risk Index: expected events per year (annualized frequency) for the hub's county.

Scoring (deterministic, done by code; every input maps to 0-100 as min(raw / cap, 1) x 100; hazard score = 50% \
observed weather + 50% FEMA, or FEMA only where there is no weather input; composite = weighted mean of hazards):
{_methodology()}

Rules:
- Every number you state must come from a tool result in this conversation. Never estimate or invent numbers. \
Call tools before answering; for "why" questions use hub_breakdown and name the inputs that drive the score.
- Scores are exposure indicators (0-100), not probabilities or dollar losses. A hub's score depends only on its own \
data, not on the other hubs; only the ranks compare hubs. Mention this only when a user could misread a score.
- Write for a business analyst, not a developer. Avoid technical terms such as "cap", "normalized", "NRI", \
"AFREQ", "reanalysis", "ERA5" or tool names; say "FEMA hazard records" and "past weather" instead. Keep the numbers.
- Hazards we do not model (earthquake, wildfire, drought, ...), hubs not in the network, or years outside the data: \
set status "out_of_scope", say what is missing, and offer the closest thing we can answer.
- If the question is ambiguous, either answer the most likely reading and state it as an assumption, or set \
status "needs_clarification" and ask one short question.
- Follow-up questions refer to earlier turns ("those hubs", "what about heat?"); resolve them from the conversation.
- Answer concisely for a business analyst: lead with the answer, then the reasoning. Plain text, '- ' bullets allowed.
- Raw inputs carry a unit: "percent of days" values are already percentages (0.55 means 0.55% of days).
- assumptions: the assumptions this specific answer relies on. uncertainty: the data limits that affect it \
(e.g. reanalysis grid cannot resolve hurricane winds; county-level FEMA data covers more than the hub site; \
5 years is a short climate record).

Today's date: {today.isoformat()}."""


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    """One shared SDK client. The SDK reads ANTHROPIC_API_KEY from the environment itself."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _blocks_to_params(content) -> list[dict]:
    """Convert response content blocks to request params, keeping thinking blocks exactly as returned."""
    return [block.model_dump(mode="json", exclude_none=True) for block in content]


def _final_text(response) -> str:
    return "".join(b.text for b in response.content if b.type == "text")


def _check_answer(raw: str) -> AgentAnswer:
    """Parse and validate the final answer. Raises ValidationError/ValueError with a message Claude can act on."""
    answer = AgentAnswer.model_validate_json(raw)
    if answer.status == "answered" and not answer.answer.strip():
        raise ValueError("status is 'answered' but the answer text is empty")
    if not answer.bottom_line.strip():
        raise ValueError("bottom_line is empty; give a one-sentence summary")
    if len(answer.bottom_line.split()) > MAX_BOTTOM_LINE_WORDS:
        raise ValueError(f"bottom_line is longer than {MAX_BOTTOM_LINE_WORDS} words; make it one short sentence")
    return answer


def run_turn(conn: sqlite3.Connection, conversation_id: str, user_message: str,
             client: anthropic.Anthropic | None = None) -> TurnResult:
    """Answer one user message in a conversation. Raises AgentError if no valid answer is produced."""
    client = client or get_client()
    settings = get_settings()
    history = conversations.load_messages(conn, conversation_id)
    turn: list[dict] = [{"role": "user", "content": [{"type": "text", "text": user_message}]}]
    tools_used: list[str] = []
    fix_attempts = 0
    # One window for the whole turn: the prompt, every tool call and the attached scores all use it, so a
    # data refresh that finishes mid-turn can't make them disagree. Raises DataNotLoadedError (-> 503).
    window = effective_window(conn)
    system = system_prompt(date.today(), window)

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=TOOL_SCHEMAS,
            messages=history + turn,
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": answer_json_schema()}},
        )
        if response.stop_reason == "refusal":
            raise AgentError("The model declined to answer this request.")
        if response.stop_reason == "max_tokens":
            raise AgentError("The model ran out of output tokens before finishing.")
        turn.append({"role": "assistant", "content": _blocks_to_params(response.content)})

        if response.stop_reason == "tool_use":
            turn.append({"role": "user", "content": _run_tools(conn, window, response.content, tools_used)})
            continue

        raw = _final_text(response)
        try:
            answer = _check_answer(raw)
        except (ValidationError, ValueError) as exc:
            if fix_attempts >= MAX_FIX_ATTEMPTS:
                raise AgentError(f"The model's answer failed validation: {exc}") from exc
            fix_attempts += 1
            log.warning("answer failed validation, asking for a fix: %s", exc)
            turn.append({"role": "user", "content": [{"type": "text", "text":
                         f"Your answer failed validation: {exc}. Reply again with a corrected answer."}]})
            continue

        conversations.append_turn(conn, conversation_id, turn)
        all_scores = scores_by_id(conn, window)
        return TurnResult(conversation_id, answer, [all_scores[h] for h in answer.hub_ids], tools_used)

    raise AgentError(f"No final answer after {MAX_TOOL_ROUNDS} model calls.")


def _run_tools(conn: sqlite3.Connection, window: Window, content, tools_used: list[str]) -> list[dict]:
    """Run every tool_use block of one response; return all results in ONE user message (parallel-call safe)."""
    results = []
    for block in content:
        if block.type != "tool_use":
            continue
        tools_used.append(block.name)
        try:
            output, is_error = run_tool(conn, block.name, block.input, window), False
        except ToolError as exc:
            output, is_error = {"error": str(exc)}, True
        log.info("tool %s(%s) error=%s", block.name, json.dumps(block.input), is_error)
        results.append({"type": "tool_result", "tool_use_id": block.id,
                        "content": json.dumps(output), "is_error": is_error})
    return results
