# AI Travel Assistant

Vacation planner backend: FastAPI, SQLAlchemy, JWT auth, trips, itineraries, and LLM-powered itinerary generation.

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

Tests mock the LLM client; they do not call Anthropic.

## Architecture

```
Client
  │
  ├─ POST /auth/register, /auth/login  →  JWT
  ├─ CRUD /trips                       →  trips table
  ├─ POST /knowledge                   →  add travel document → LanceDB vector store
  ├─ GET  /knowledge/search            →  semantic search over knowledge base
  └─ POST /itineraries                 →  manual days OR LLM generation
         │
         ├─ manual: client sends days[]
         └─ generate=true: load trip from DB
                │
                ▼
         app/services/llm_itinerary.py
                │
                ├─ RAG: search knowledge base for destination context
                │       │
                │       ▼
                │  app/services/knowledge_base.py
                │       │
                │       ▼
                │  LanceDB (vector store, ./vector_store)
                │       │
                └───────┘  context injected into system prompt
                │
                ├─ tool call: get_current_weather
                │       │
                │       ▼
                │  app/services/weather.py  →  OpenWeatherMap API
                │       │
                └───────┘
                │
                ▼
         Anthropic Claude Messages API
         (retries up to LLM_MAX_RETRIES on bad output)
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
| Services | `app/services/` | Audit logging, LLM generation, weather lookup, knowledge base |
| Dependencies | `app/deps.py` | Bearer token → current user |

Tables are created on startup (`create_all` in `app/main.py`); there are no migrations in this repo.

## LLM integration

Provider: **Anthropic Claude** via the official `anthropic` Python SDK.

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | (empty) | API key from [console.anthropic.com](https://console.anthropic.com) |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Claude model |
| `ANTHROPIC_TEMPERATURE` | `0.7` | Creativity vs consistency |
| `ANTHROPIC_MAX_TOKENS` | `2000` | Upper bound on response length |
| `LLM_MAX_RETRIES` | `2` | Retry attempts when the LLM returns unparseable output |
| `WEATHER_API_KEY` | (empty) | OpenWeatherMap API key; enables the weather tool |
| `VECTOR_STORE_PATH` | `./vector_store` | Directory where LanceDB persists the knowledge base |

### Prompt design

**System prompt** (`app/services/llm_itinerary.py`) — stable rules: JSON-only output, exact day count, activities within the destination, respect budget and travel style, no prices or booking links.

**User prompt** — built from trip fields loaded from the database:

```
Plan a {days}-day trip to {destination} with a budget of {budget}.
The travel style is {trip_style}.
```

The user prompt adds constraints for local-only activities, realistic pacing, and the exact number of days.

### API usage

Manual itinerary (unchanged):

```bash
curl -X POST http://127.0.0.1:8000/itineraries \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"trip_id": 1, "days": [{"day": 1, "activities": ["Eiffel Tower"]}]}'
```

AI-generated itinerary:

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

The LLM is required to return JSON in a fixed shape (`{"days": [{"day": N, "activities": [...]}]}`). `app/services/llm_itinerary.py` validates every field: day count, consecutive numbering, no duplicates, activities as strings. Invalid responses raise `LLMResponseError` and trigger a retry.

### Retry on invalid output

If the LLM returns malformed or structurally incorrect JSON, the service retries the full LLM call up to `LLM_MAX_RETRIES` times (default `2`, so three attempts total). API-level failures (network errors, auth) are not retried and surface immediately as `502`.

### Weather tool

When `WEATHER_API_KEY` is set, the LLM is offered a `get_current_weather` tool via Anthropic's tool use API. Claude may call this before generating the itinerary to incorporate live weather conditions into activity planning. If the weather API is unavailable, the error is returned as the tool result and generation continues without weather context.

The weather service lives in `app/services/weather.py` and calls the OpenWeatherMap `/data/2.5/weather` endpoint.

### Model behavior

- **Temperature** `0.7` balances varied suggestions with repeatable structure.
- **System prompt** instructs Claude to return parseable JSON matching `{"days": [...]}`.
- **max_tokens** `2000` is enough for multi-day plans with several activities per day.

### Limitations

- The model may suggest venues that do not exist or are closed; output is not verified against live data.
- Budget is guidance only — no real-time pricing or currency conversion.
- Destination scope relies on prompt instructions; the model may occasionally suggest nearby cities.
- AI generation requires a valid `ANTHROPIC_API_KEY`; otherwise the API returns `503`.
- Weather tool requires a valid `WEATHER_API_KEY`; without it the tool is simply not offered to the model.

## RAG (Retrieval-Augmented Generation)

The knowledge base allows you to store curated travel documents (guides, local tips, hidden gems, FAQs) that the AI uses when generating itineraries.

### How it works

1. **Add documents** — `POST /knowledge` stores a travel document in the LanceDB vector store.
2. **Embedding** — each document is embedded using feature-hashing (bag-of-words, 384 dimensions, cosine similarity). No external embedding API is needed.
3. **Retrieval** — when `generate: true` is called, the system searches the vector store for the top-3 most relevant documents for the destination.
4. **Augmentation** — retrieved documents are injected into the Claude system prompt under a `### Local Knowledge` section before generation begins.
5. **Fallback** — if the knowledge base is empty or unavailable, generation continues normally without context.

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

LanceDB is used as the vector store, persisted to `./vector_store` by default. Embeddings use a feature-hashing approach (pure Python + numpy) — no external embedding model or API key required. In a production system this would be replaced with a dedicated embedding model such as Voyage AI or sentence-transformers.

## Layout

Routers live under `app/routers/`, Pydantic models under `app/schemas/`, tables under `app/models/`, config and DB under `app/core/`, shared auth dependency in `app/deps.py`. `app/services/` holds audit logging, LLM generation, weather lookup, and the knowledge base.

`POST /itineraries` supports manual `days` or `generate: true` for AI. Responses include a `message` field; full request/response shapes are in `/docs`.
