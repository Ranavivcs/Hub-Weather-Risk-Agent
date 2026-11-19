# Design

## Goal and scope

Help analysts choose which hubs to invest in by answering questions about hub weather exposure: rankings,
comparisons, weather statistics and "why" explanations, with follow-ups. Deliberately narrow: 15 hubs, five
hazards, five years of history, one deterministic score. The score measures **exposure** (0–100): how often disruptive weather hits a hub.
It is not a probability, and not a dollar loss.

## Architecture

```
 Browser (React chat)
     │  POST /api/chat {message, conversation_id}
     ▼
 FastAPI (app/main.py) ─── also serves the built UI and GET /api/hubs, /api/health
     │
     ▼
 Agent loop (app/agent.py) ◄──────────────► Claude Haiku (Anthropic Messages API)
     │  runs the tools Claude asks for         tools + JSON-schema output (output_config.format)
     ▼
 Tools (app/tools.py) ──► risk.py ──► scoring.py   (pure, deterministic, unit-tested)
     │                      │
     ▼                      ▼
 SQLite (data/weather.db) ◄── ingest.py ◄── Open-Meteo Historical API, FEMA NRI (ArcGIS API)
     ▲
     └── alerts.py ── POST JSON ──► ALERT_WEBHOOK_URL        (triggered by POST /api/alerts/check or CLI)
```

One request, step by step:
1. The UI POSTs the message (and the conversation id for follow-ups).
2. The agent loads the conversation history from SQLite and calls Claude with the history, five tool schemas
   and the answer JSON schema.
3. Claude asks for tools (for example `hub_breakdown("dallas")`). Our code runs them against SQLite and the
   scoring module, and sends the results back. This repeats until Claude writes its final answer (at most 8 rounds).
4. The final answer is JSON that the API constrains to our schema. We validate it again with Pydantic
   (`AgentAnswer`); if it fails our checks, Claude gets one chance to fix it.
5. Code attaches the deterministic scores for the hubs the answer names. Then the whole turn is stored in a single
   transaction, and the response goes back to the UI.

**Division of labour.** The LLM decides which analysis answers the question, and explains it. Code computes every
number: scores, ranks and day counts. The score table in the UI comes from code, not from the LLM's text.
The eval also checks that the numbers in the LLM's text match what the code computes.

## Deterministic scoring (`app/scoring.py`)

Five hazards with equal weights (20% each):

| Hazard | Observed weather (% of days, 2021–2025) | FEMA NRI (expected events/yr, county) |
|---|---|---|
| Winter | ≥ 1 cm snow; min ≤ −10 °C | winter weather, ice storm, cold wave |
| Hurricane | none: reanalysis can't resolve hurricane winds | hurricane |
| Flood | ≥ 50 mm precipitation | riverine flood, coastal flood |
| Heat | max ≥ 35 °C | heat wave |
| Severe storm | gusts ≥ 60 km/h | tornado, hail, strong wind |

- The hazard types are FEMA's. FEMA lists 18; we use the 10 that are weather-driven and disrupt logistics.
  Earthquake, wildfire, drought, landslide, avalanche, tsunami, volcanic activity and lightning are out of scope.
  **Grouping the 10 into these 5 hazards is our choice**, for readability; FEMA does not group them.
- Each raw input maps to 0–100 with a fixed cap: `min(raw / cap, 1) × 100`. Caps sit near the high end of large
  US cities, so 100 means "about as bad as a major US hub gets".
- Hazard score = 50% observed weather + 50% FEMA. Hurricane uses FEMA only.
- Composite = weighted mean of the five hazard scores.

Choices made with the user:
- **Five hazards, not four.** Severe storm was added because Dallas's dominant exposure is hail and tornadoes
  (FEMA: ~8.9 hail and ~0.9 tornado events/yr).
- **FEMA `AFREQ` (events per year), not `RISKS`.** The composite `RISKS` score multiplies the hazard by the value
  exposed in the county, so every big-city county is ~99 on almost everything and the hubs can't be told apart.
- **Fixed caps, not ranking hubs against each other.** A hub's score depends only on its own data, so a score
  change means that hub's data changed, which matters for alerts.
- **Equal weights.** They are the easiest to defend without business loss data. They are a single config value
  (`HAZARD_WEIGHTS`).

## Structured output (LLM ↔ code contract)

`AgentAnswer` (`app/schemas.py`) has these fields: `status` (answered / out_of_scope / needs_clarification),
`answer`, `bottom_line` (one-sentence summary shown at the end of each answer), `hub_ids` (an enum of the 15 hub ids), `hazards` (an enum), `assumptions`, `uncertainty`.
- The Messages API enforces the schema via `output_config.format`.
- Pydantic re-validates it, plus business checks.
- Tool inputs use `strict: true` schemas; our handlers still validate hub names, years and metrics, and return
  clear errors to the LLM.

## Repository structure

```
app/
  main.py           FastAPI app: endpoints, error mapping, serves the UI
  agent.py          the tool-use loop, system prompt, answer validation
  tools.py          tool schemas + handlers (the only things the LLM can call)
  schemas.py        Pydantic models: AgentAnswer (LLM contract) and API request/response
  scoring.py        pure deterministic scoring (no I/O)
  risk.py           reads raw inputs from SQLite, calls scoring
  metrics.py        "% of days where X" SQL metrics
  hubs.py           the hub network (config)
  conversations.py  conversation/message persistence
  db.py             SQLite schema + connection
  ingest.py         loads Open-Meteo + FEMA data (python -m app.ingest)
  sources/          thin clients for the two public APIs
  alerts.py         score-change alerts: snapshot, compare, webhook (python -m app.alerts)
  rate_limit.py     per-IP limit for /api/chat
  window.py         the data window: target (what ingest fetches) vs effective (what scores use)
  config.py         settings from environment / .env
frontend/src/       React UI: App.tsx (chat), Sidebar.tsx (ranking / "How we rank" tabs),
                    AnswerCard.tsx (reasoning, score table, bottom line, caveats), RankingPanel.tsx
                    (GET /api/hubs), MethodPanel.tsx, useSpeechInput.ts (voice), RichText.tsx,
                    ScoreCell.tsx, hazards.ts, brand.ts, ErrorBoundary.tsx, api.ts
tests/              pytest: scoring, schemas/tools, agent loop with a fake LLM, alerts, API, window/ingest
evals/              cases.json + run.py (real LLM, ground truth from code)
docs/ai-session/    the AI session transcripts (readable versions)
```

## Data storage: SQLite

Tables:
- `weather_daily(hub_id, date, snowfall_cm, precip_mm, gust_max_kmh, tmax_c, tmin_c)`: 15 × 1,826 rows
- `nri_county(county_fips, field, value, fetched_at)`
- `conversations(id, created_at)`
- `messages(id, conversation_id, role, content_json, created_at)`
- `score_snapshots(id, hub_id, computed_at, composite, breakdown_json)`: one row per hub per alert check;
  the alert compares against each hub's latest row

Why SQLite:
- The data is small (~27k weather rows).
- It is written once by the ingest and read many times.
- It needs no server and is one file to explain and ship.
- Scores are cheap to compute on every request (a few SQL aggregates), so they aren't cached.

Messages are stored as the exact API content blocks, including Claude's `thinking` blocks, because they must be
sent back unchanged on follow-up turns. A turn is written only after it succeeds, so a failed turn never leaves
half a tool exchange in the history.

When to move to Postgres: several app instances or writers, many more hubs or years, or analysts needing shared
history across deployments. The SQL is plain enough to port.

## Score-change alerts (bonus)

`app/alerts.py` does the following:
1. Recompute every hub's score.
2. Compare it with the hub's latest row in `score_snapshots`.
3. Store the new snapshot.
4. POST a JSON alert to `ALERT_WEBHOOK_URL` for every hub whose overall score moved by at least `ALERT_THRESHOLD`
   points (default 1). The alert includes the per-hazard deltas, so it shows what moved.

The first run only records a baseline.

- **Why scores change.** With the default fixed window (2021–2025) they never change, so `DATA_END=latest` makes
  the 5-year window roll forward. The ingest is incremental: a daily refresh fetches only the new days, one small
  call per hub. A FEMA data update also changes scores.
- **Two windows (`app/window.py`), both computed when called, never at import.** An earlier version computed
  the window once at import; an external review found that this froze a long-running server's window, so a daily
  refresh fetched nothing and no alert could fire.
  - **Target window:** what `DATA_END` asks for. Only ingest uses it, to decide what to download.
  - **Effective window:** what everything the user sees uses: scores, the "last year" in the agent's prompt,
    `weather_stats` years and periods, and alert snapshots. It ends at the earlier of the target end and the last
    day stored for every hub, and always spans 5 full years.
  
  So after a restart, when the database only holds the data baked into the image (through 2025), scores use the
  full 2021–2025 window instead of a partly empty one. A refresh then moves the window forward.
  - The effective window is computed once per chat turn, API request or alert check, and passed down. A refresh
    that finishes mid-turn therefore can't give the prompt and the tools different windows.
  - `GET /api/health` shows the window in use (`data_window`) next to the configured `target_end`.
- **Triggers.**
  - `python -m app.alerts [--refresh]`.
  - `POST /api/alerts/check?refresh=true` with header `X-Alert-Token` (`ALERT_TOKEN`). It returns `202` and runs
    in the background, so an external scheduler such as cron-job.org can call it daily without hitting its timeout.
  - The endpoint is disabled while `ALERT_TOKEN` is unset.
- **Live setup.** The Render service runs with `DATA_END=latest`. A daily cron-job.org job calls
  `POST /api/alerts/check?refresh=true` with the token, and alerts go to a webhook.site inbox. It was verified
  end to end: a baseline on the image's data (through 2025), then a refresh with 2026 weather, sent the alert
  to the inbox.
- **Verified with real data.** A baseline on 2021–2025, then a rolled-forward window (+316 days of 2026 weather),
  flagged Houston −1.7 and Miami +1.2.
- **Limit on Render's free plan.** Snapshots live in the container's SQLite file, so a restart or redeploy wipes
  them. **The first check after a restart only records a new baseline**, and alerts resume from the next check.
  The data downloaded since the image was built is wiped too. Until the next refresh, scores fall back to the
  image's full 2021–2025 window, not a partial one. The alert job runs inside the web service on purpose:
  a separate cron service couldn't see that file. Persistent alert history would need Postgres.

## Voice input (bonus)

The composer has a mic button that uses the browser's built-in Web Speech API. Speech is transcribed into the
message box; the user reviews it and presses Send, and nothing is sent automatically. It works in Chrome and
Edge, and the button is hidden where the API is unsupported. There is no backend change.

## Deployment

There is one Docker image and one Render web service. The UI and API share an origin, so no CORS setup is needed.

- **Data is baked in.** The ingest runs during the image build, so the live service doesn't call Open-Meteo
  or FEMA at runtime.
- **Conversations reset on redeploy.** Render's free disk is ephemeral; persistent history would need Render's
  Postgres or a disk.
- **Chat is rate-limited per IP.** This protects the API bill on a public URL. It is in-memory, which is fine for
  one instance; several instances would need a shared store.

## Assumptions

- **The hub network is ours.** The brief names no hubs. We chose 15 well-known US freight cities: every city the
  example questions name, six in the Midwest, and a spread of hazard profiles. Coordinates are city centers.
- **Regions follow the US Census Bureau.**
- **"Last year" means 2025**, the latest full year in the data (with a rolling window: the latest full year in it).
- **"Had snowfall" means ≥ 0.1 cm (measurable).** The winter score uses ≥ 1 cm.
- **Disruption thresholds** (1 cm snow, −10 °C, 50 mm rain, 35 °C, 60 km/h gusts) are reasonable operating
  thresholds, not company data. They should be calibrated against actual hub closure records.
- **Equal hazard weights.** With loss or closure data, weights should follow cost.

## Uncertainty and limitations

- **Coarse weather grid.** Open-Meteo historical data is ERA5-based reanalysis on a ~25 km grid. It smooths local
  extremes and underestimates gusts. It cannot resolve hurricane winds, so the hurricane hazard relies on FEMA only.
- **County-level FEMA data.** FEMA values describe the whole county, not the hub site. For example, Los Angeles
  County's winter and flood frequencies include its mountains and coast.
- **Five years is a short record** for rare events: one bad season can move a score.
- **Some overlap between hazards.**
  - The gust input (days with gusts of 60 km/h or more) counts any windy day, including winter storms and the edge
    of a hurricane, not only thunderstorms.
  - A hurricane's rain counts toward Flood, because heavy rain is scored there.
  
  So a single event can raise two hazards. FEMA's frequencies keep the hazard types separate, which limits this.
- **Exposure, not consequence.** The score measures how often a hazard occurs, not how much a closure costs at a
  given hub, and not how resilient the hub already is.
- **The LLM can still phrase things imprecisely.** Numbers in the score table are always from code. The eval
  checks the numbers in its text too.
