# Hub Weather Risk Agent

A chat agent that helps logistics analysts decide which US distribution hubs are most exposed to weather
disruption. It ranks 15 hubs with a deterministic scoring model built on public data (Open-Meteo historical
weather 2021–2025 and the FEMA National Risk Index), and uses Claude Haiku to pick the right analysis and
explain it. The LLM never computes a score; code does.

**Live demo:** https://hub-weather-risk-agent.onrender.com (chat; API docs at `/docs`).
Design, architecture and assumptions: [DESIGN.md](DESIGN.md).

The live service uses a rolling data window (`DATA_END=latest`), so its scores include the newest weather and
differ slightly from the fixed 2021–2025 numbers in DESIGN.md and the eval, which uses the fixed window so its
results can be reproduced. A daily scheduled job calls the alert check, and alerts go to a webhook.

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
time). In Render, either **New → Web Service** (runtime Docker, health check `/api/health`) or **New → Blueprint**
(reads `render.yaml`). Set `ANTHROPIC_API_KEY` as an environment variable in the dashboard. `/api/chat` is limited to `CHAT_LIMIT_PER_HOUR` (default 20)
messages per client IP. Conversations live in the container's SQLite file and reset on each redeploy.

Local check of the image: `docker build -t hub-weather-risk-agent .` then
`docker run --rm -p 8000:8000 --env-file .env hub-weather-risk-agent`.

## API

| Method & path | Purpose |
|---|---|
| `POST /api/chat` | Send a message. Body `{"message": "...", "conversation_id": null}`; omit/null the id to start a conversation, pass the returned id back for follow-ups. Returns the structured answer, the code-computed scores of the hubs it names, and the tools used. |
| `GET /api/hubs?hazard=&region=` | Deterministic scores for all hubs, most exposed first. No LLM. |
| `GET /api/health` | Status, whether data is loaded, whether an API key is configured. |
| `POST /api/alerts/check?refresh=` | Score-change alert check (header `X-Alert-Token`). Returns 202 and runs in the background. Disabled until `ALERT_TOKEN` is set. |

Example:

```powershell
curl.exe -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{\"message\": \"Why is Dallas high risk?\"}'
```

## Score-change alerts and voice (bonus)

```powershell
# Record a baseline, then check again later (or after new data) and alert on changes
.venv\Scripts\python -m app.alerts
.venv\Scripts\python -m app.alerts --refresh
```

- Set `ALERT_WEBHOOK_URL` (for example a webhook.site URL) to receive the JSON alert.
- `DATA_END=latest` makes the 5-year window roll forward, so scores follow new weather.
- To schedule it, set `ALERT_TOKEN` and have a cron service call `POST /api/alerts/check?refresh=true` daily with
  header `X-Alert-Token`.
- **Voice:** click 🎤 in the message box (Chrome or Edge) and speak your question, then press Send.
