# AI Travel Assistant

Vacation planner backend: FastAPI, SQLAlchemy, JWT auth, trips, itineraries, and an AI agent that orchestrates multiple tools to generate itineraries.

## Run it

Python 3.11+ (3.12 is fine). From the repo root:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env` — you need `DATABASE_URL`, `JWT_SECRET_KEY`, and `ANTHROPIC_API_KEY` for AI generation. SQLite is enough locally (`sqlite:///./ai_travel_assistant.db` is in `.env.example`). Postgres works too if you change the URL; `psycopg` is already in `requirements.txt`.

Start the server:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/docs** to try the API (Swagger). Health check: `GET /health`.

## Tests

```bash
python -m pytest -q
```

Tests mock the LLM and all external services; they do not call Anthropic, OpenWeatherMap, or OpenTripMap.

## Architecture

```
Client
  │
  ├─ POST /auth/register, /auth/login  →  JWT
  ├─ CRUD /trips                       →  trips table
  ├─ POST /knowledge                   →  add travel document → LanceDB vector store
  ├─ GET  /knowledge/search            →  semantic search over knowledge base
  └─ POST /itineraries                 →  manual days OR agent-generated
         │
         ├─ manual: client sends days[]
         └─ generate=true: load trip from DB
                │
                ▼
         app/services/llm_itinerary.py
                │
                ▼
         app/services/agent.py  (LangGraph)
                │
         ┌──────┴──────────────────────────────────┐
         │         Step 1: Gather (ReAct agent)     │
         │                                          │
         │  ┌─────────────────────────────────┐     │
         │  │ weather_tool  → OpenWeatherMap   │     │
         │  │ knowledge_tool → LanceDB KB      │     │
         │  │ places_tool   → OpenTripMap API  │     │
         │  │ pricing_tool  → internal logic   │     │
         │  └─────────────────────────────────┘     │
         │  Agent decides which tools to call       │
         └──────────────────────────────────────────┘
                │
                │  context summary
                ▼
         Step 2: Format (dedicated LLM call)
         Produces {"days": [...]} JSON
                │
                ▼
         parse + validate + retry (up to LLM_MAX_RETRIES)
                │
                ▼
         upsert itineraries table + audit log
```

| Layer | Location | Role |
|-------|----------|------|
| Routers | `app/routers/` | HTTP endpoints |
| Schemas | `app/schemas/` | Request/response validation (Swagger) |
| Models | `app/models/` | SQLAlchemy tables |
| Core | `app/core/` | Config, database, JWT |
| Services | `app/services/` | Audit logging, LLM agent, tools, weather, knowledge base |
| Dependencies | `app/deps.py` | Bearer token → current user |

Tables are created on startup (`create_all` in `app/main.py`); there are no migrations in this repo.

## Agent and Tools

The itinerary generator is a two-step LangGraph workflow.

**Step 1 — Gather** runs a ReAct agent that decides which tools are relevant and calls them. The four available tools are:

| Tool | Source | What it provides |
|------|--------|-----------------|
| `weather_tool` | OpenWeatherMap | Current conditions at the destination |
| `knowledge_tool` | LanceDB knowledge base | Curated travel tips stored via `POST /knowledge` |
| `places_tool` | OpenTripMap API | Nearby attractions and points of interest |
| `pricing_tool` | Internal estimator | Whether the budget is tight, moderate, or comfortable for the region |

The agent does not call every tool on every request — it decides based on the destination and request context.

**Step 2 — Format** takes the gathered context summary and makes a second, structured LLM call that produces the final `{"days": [...]}` JSON. This separates information gathering from output formatting, which makes the JSON output more reliable.

Both steps use the same Claude model configured in `ANTHROPIC_MODEL`.

## LLM integration

Provider: **Anthropic Claude** via **LangChain** (`langchain-anthropic`) orchestrated by **LangGraph**.

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | (empty) | API key from console.anthropic.com |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Claude model used for both agent steps |
| `ANTHROPIC_TEMPERATURE` | `0.7` | Creativity vs consistency |
| `ANTHROPIC_MAX_TOKENS` | `2000` | Upper bound on response length |
| `LLM_MAX_RETRIES` | `2` | Retry attempts when the agent returns unparseable JSON |
| `WEATHER_API_KEY` | (empty) | OpenWeatherMap key; enables the weather tool |
| `OPENTRIPMAP_API_KEY` | (empty) | OpenTripMap key; enables the places tool |
| `VECTOR_STORE_PATH` | `./vector_store` | Directory where LanceDB persists the knowledge base |

`WEATHER_API_KEY` and `OPENTRIPMAP_API_KEY` are optional. If either is missing, the corresponding tool returns a "not configured" message and the agent continues without it.

### API usage

Manual itinerary (unchanged):

```bash
curl -X POST http://127.0.0.1:8000/itineraries \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"trip_id": 1, "days": [{"day": 1, "activities": ["Eiffel Tower"]}]}'
```

AI-generated itinerary (agent runs, calls tools, generates plan):

```bash
curl -X POST http://127.0.0.1:8000/itineraries \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"trip_id": 1, "generate": true}'
```

Response shape (both modes):

```json
{
  "trip_id": 1,
  "itinerary": [
    {"day": 1, "activities": ["..."]}
  ],
  "message": "Itinerary generated successfully"
}
```

### Structured output and validation

The format step instructs Claude to return JSON in a fixed shape (`{"days": [{"day": N, "activities": [...]}]}`). `app/services/llm_itinerary.py` validates every field: day count, consecutive numbering, no duplicates, activities as strings. Invalid responses raise `LLMResponseError` and trigger a full retry of both agent steps.

### Limitations

- The model may suggest venues that do not exist or are closed; output is not verified against live data.
- `pricing_tool` uses a static regional cost table — not live pricing or currency conversion.
- Destination scope relies on prompt instructions; the model may occasionally suggest nearby cities.
- AI generation requires a valid `ANTHROPIC_API_KEY`; otherwise the API returns `503`.
- `places_tool` requires a valid `OPENTRIPMAP_API_KEY`; without it the tool is skipped silently.
- `weather_tool` requires a valid `WEATHER_API_KEY`; without it the tool is skipped silently.

## RAG (knowledge base)

The knowledge base stores curated travel documents that the agent can retrieve via `knowledge_tool`.

### How it works

1. **Add documents** — `POST /knowledge` stores a travel document in LanceDB.
2. **Embedding** — each document is embedded using feature-hashing (bag-of-words, 384 dimensions). No external embedding API required.
3. **Retrieval** — the agent calls `knowledge_tool` with a search query; it returns the top-3 most relevant documents.
4. **Fallback** — if the knowledge base is empty or unavailable, the tool returns a message saying so and generation continues.

### API usage

Add a travel document:

```bash
curl -X POST http://127.0.0.1:8000/knowledge \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Hidden gems in Paris",
    "content": "Visit the covered passages like Galerie Vivienne. The Promenade Plantée is a green walkway built on an old railway viaduct.",
    "destination": "Paris",
    "category": "hidden gems"
  }'
```

Search the knowledge base:

```bash
curl "http://127.0.0.1:8000/knowledge/search?query=Paris+outdoor+activities&limit=3" \
  -H "Authorization: Bearer <token>"
```

### Vector store

LanceDB is persisted to `./vector_store` by default. Embeddings use a feature-hashing approach (pure Python + numpy) — no external embedding model or API key required.

## Layout

```
app/
  core/         config, database, JWT security
  models/       SQLAlchemy tables (User, Trip, Itinerary)
  schemas/      Pydantic request/response shapes
  routers/      HTTP endpoints (auth, users, trips, itineraries, knowledge, health)
  services/
    agent.py              LangGraph two-step workflow
    llm_itinerary.py      public interface: generate_itinerary_days()
    knowledge_base.py     LanceDB vector store
    weather.py            OpenWeatherMap HTTP client
    audit_log.py          structured logging
    tools/
      weather_tool.py     LangChain tool wrapping weather.py
      knowledge_tool.py   LangChain tool wrapping knowledge_base
      places_tool.py      LangChain tool calling OpenTripMap
      pricing_tool.py     LangChain tool with internal cost estimator
  deps.py       Bearer token → current user dependency
tests/
  test_agent.py           agent workflow tests
  test_tools.py           individual tool tests
  test_llm_itinerary.py   generate_itinerary_days() tests
  test_itineraries.py     router integration tests
  ...
```
