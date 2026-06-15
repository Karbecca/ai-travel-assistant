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
  └─ POST /itineraries                 →  manual days OR LLM generation
         │
         ├─ manual: client sends days[]
         └─ generate=true: load trip from DB
                │
                ▼
         app/services/llm_itinerary.py
                │
                ▼
         Anthropic Claude Messages API
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
| Services | `app/services/` | Audit logging, LLM itinerary generation |
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

### Model behavior

- **Temperature** `0.7` balances varied suggestions with repeatable structure.
- **System prompt** instructs Claude to return parseable JSON matching `{"days": [...]}`.
- **max_tokens** `2000` is enough for multi-day plans with several activities per day.

### Limitations

- The model may suggest venues that do not exist or are closed; output is not verified against live data.
- Budget is guidance only — no real-time pricing or currency conversion.
- Destination scope relies on prompt instructions; the model may occasionally suggest nearby cities.
- AI generation requires a valid `ANTHROPIC_API_KEY`; otherwise the API returns `503`.

## Layout

Routers live under `app/routers/`, Pydantic models under `app/schemas/`, tables under `app/models/`, config and DB under `app/core/`, shared auth dependency in `app/deps.py`. `app/services/` holds audit logging and LLM itinerary generation.

`POST /itineraries` supports manual `days` or `generate: true` for AI. Responses include a `message` field; full request/response shapes are in `/docs`.
