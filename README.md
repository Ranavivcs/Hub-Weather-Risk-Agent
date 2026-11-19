# Hub Weather Risk Agent

A chat agent that helps logistics analysts decide which US distribution hubs are most exposed to weather
disruption. It ranks 15 hubs with a deterministic scoring model built on public data (Open-Meteo historical
weather 2021–2025 and the FEMA National Risk Index), and uses Claude Haiku to pick the right analysis and
explain it. The LLM never computes a score; code does.

Design, architecture and assumptions: [DESIGN.md](DESIGN.md).

## Run it locally

Requirements: Python 3.12, Node 20+, an Anthropic API key.

```powershell
# 1. Backend dependencies
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt

# 2. Configuration: copy the example and paste your key into .env
copy .env.example .env

# 3. Load the public data into SQLite (about a minute; safe to re-run)
.venv\Scripts\python -m app.ingest

# 4. Build the chat UI (FastAPI serves it)
cd frontend; npm install; npm run build; cd ..

# 5. Start the server
.venv\Scripts\uvicorn app.main:app --port 8000
```

Open http://localhost:8000 for the chat, or http://localhost:8000/docs for the interactive API docs.

For UI development with hot reload, run `npm run dev` in `frontend/` (port 5173, proxies `/api` to :8000).

## Tests and evaluation

```powershell
# Unit tests: scoring, schema validation, tools, agent loop with a fake LLM. No network, no API key.
.venv\Scripts\python -m pytest

# Evaluation set: 12 questions against the real agent (calls Claude; costs a few cents).
.venv\Scripts\python -m evals.run
.venv\Scripts\python -m evals.run --case dallas_why
```

## Deploy (Render)

`Dockerfile` builds the UI, installs the API and bakes the public data into the image (ingest runs at build
time). `render.yaml` defines one free Docker web service. In Render: **New → Blueprint**, pick this repo,
and enter `ANTHROPIC_API_KEY` when prompted. `/api/chat` is limited to `CHAT_LIMIT_PER_HOUR` (default 20)
messages per client IP. Conversations live in the container's SQLite file and reset on each redeploy.

Local check of the image: `docker build -t hub-weather-risk-agent .` then
`docker run --rm -p 8000:8000 --env-file .env hub-weather-risk-agent`.

## API

| Method & path | Purpose |
|---|---|
| `POST /api/chat` | Send a message. Body `{"message": "...", "conversation_id": null}`; omit/null the id to start a conversation, pass the returned id back for follow-ups. Returns the structured answer, the code-computed scores of the hubs it names, and the tools used. |
| `GET /api/hubs?hazard=&region=` | Deterministic scores for all hubs, most exposed first. No LLM. |
| `GET /api/health` | Status, whether data is loaded, whether an API key is configured. |

Example:

```powershell
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{\"message\": \"Why is Dallas high risk?\"}'
```
