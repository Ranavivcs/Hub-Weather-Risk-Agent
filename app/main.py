"""FastAPI app: the agent's HTTP API, plus the built React chat UI served from the same origin.

Run: `uvicorn app.main:app --reload`  ->  API docs at http://localhost:8000/docs
"""

import logging
import os
import sqlite3
from collections.abc import Iterator
from typing import Literal

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles

from app import agent, conversations
from app.config import REPO_ROOT, get_settings
from app.db import connect
from app.hubs import REGIONS
from app.rate_limit import RateLimiter
from app.risk import DataNotLoadedError
from app.schemas import ChatRequest, ChatResponse, HubScoreOut
from app.scoring import HAZARDS
from app.tools import scores_by_id

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
for noisy in ("httpx", "httpx2"):  # the Anthropic SDK logs every request at INFO
    logging.getLogger(noisy).setLevel(logging.WARNING)

app = FastAPI(title="Hub Weather Risk Agent", version="1.0")


def get_conn() -> Iterator[sqlite3.Connection]:
    """One SQLite connection per request (sqlite3 connections must not be shared across threads)."""
    conn = connect(get_settings().db_path)
    try:
        yield conn
    finally:
        conn.close()


@app.get("/api/health")
def health(conn: sqlite3.Connection = Depends(get_conn)) -> dict:
    """Liveness plus readiness: is data loaded, is an API key configured. GET: read-only, safe to repeat."""
    loaded = conn.execute("SELECT COUNT(*) FROM weather_daily").fetchone()[0] > 0
    return {"status": "ok", "data_loaded": loaded, "model": get_settings().anthropic_model,
            "api_key_configured": bool(os.getenv("ANTHROPIC_API_KEY"))}


@app.get("/api/hubs", response_model=list[HubScoreOut])
def list_hub_scores(
    hazard: Literal[HAZARDS] | None = Query(None, description="Sort by this hazard; default = composite"),
    region: Literal[REGIONS] | None = Query(None, description="Only hubs in this US Census region"),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[HubScoreOut]:
    """Deterministic scores for all hubs, most exposed first. No LLM involved. GET: read-only."""
    try:
        scores = list(scores_by_id(conn).values())  # already in composite-rank order
    except DataNotLoadedError as exc:
        raise HTTPException(503, str(exc)) from exc
    if region:
        scores = [s for s in scores if s.region == region]
    if hazard:
        scores.sort(key=lambda s: (-s.hazards[hazard], s.hub_id))
    return scores


_chat_limiter = RateLimiter(get_settings().chat_limit_per_hour, window_seconds=3600)


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> ChatResponse:
    """Send one message to the agent. POST: it creates state (conversation, messages) and carries a body.

    Omit `conversation_id` to start a conversation; pass the returned id back for follow-up questions.
    Limited per client IP (CHAT_LIMIT_PER_HOUR); over the limit returns 429.
    """
    client_ip = request.client.host if request.client else "unknown"
    if not _chat_limiter.allow(client_ip):
        raise HTTPException(429, "Too many questions from this address; please try again later.")
    if req.conversation_id is None:
        conversation_id = conversations.create(conn)
    elif conversations.exists(conn, req.conversation_id):
        conversation_id = req.conversation_id
    else:
        raise HTTPException(404, "Unknown conversation_id")
    try:
        result = agent.run_turn(conn, conversation_id, req.message)
    except DataNotLoadedError as exc:
        raise HTTPException(503, str(exc)) from exc
    except anthropic.AuthenticationError as exc:
        raise HTTPException(503, "Anthropic API key missing or invalid (set ANTHROPIC_API_KEY in .env)") from exc
    except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as exc:
        raise HTTPException(503, f"LLM service temporarily unavailable: {type(exc).__name__}. Try again.") from exc
    except anthropic.APIStatusError as exc:
        raise HTTPException(502, f"LLM request failed ({exc.status_code})") from exc
    except agent.AgentError as exc:
        raise HTTPException(502, str(exc)) from exc
    return ChatResponse(conversation_id=result.conversation_id, answer=result.answer,
                        hub_scores=result.hub_scores, tools_used=result.tools_used)


# The built chat UI (frontend/dist). Mounted last so /api routes take precedence.
_DIST = REPO_ROOT / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="ui")
