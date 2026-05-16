# AI Travel Assistant

FastAPI backend for the **AI Vacation Planner** coursework: users, JWT auth, trips, itineraries, and post-write audit logging via background tasks.

## Requirements

- Python 3.11+ (3.12+ recommended)
- pip

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

python -m pip install -r requirements.txt
copy .env.example .env          # Windows; use cp on Unix
```

Edit `.env`: set `DATABASE_URL` and `JWT_SECRET_KEY` (use a long random string; never commit real secrets).

**Local SQLite (simplest):**

```env
DATABASE_URL=sqlite:///./ai_travel_assistant.db
JWT_SECRET_KEY=your-dev-secret-at-least-32-characters-long
```

Run the API:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- **Swagger UI:** http://127.0.0.1:8000/docs  
- **Health:** `GET http://127.0.0.1:8000/health`

## Tests

```bash
python -m pytest -q
```

## Architecture (short)

| Layer | Role |
|--------|------|
| `app/routers/` | HTTP routes; dependencies for DB session and current user |
| `app/schemas/` | Pydantic request/response models |
| `app/models/` | SQLAlchemy tables |
| `app/core/` | Settings, DB engine/session, security (JWT, passwords) |
| `app/services/` | Non-route helpers (e.g. audit logging used by `BackgroundTasks`) |
| `app/deps.py` | Shared FastAPI dependencies (`get_current_user`) |

SQLAlchemy `Base.metadata.create_all` runs on app startup (see `app/main.py` lifespan) so tables exist without a separate migration step for local work.

## Environment variables

See `.env.example` for all keys. Important ones:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLAlchemy URL (SQLite file or PostgreSQL via `postgresql+psycopg://…`) |
| `JWT_SECRET_KEY` | Secret for signing access tokens |
| `JWT_ALGORITHM` | Default `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime (default one week in code) |
| `APP_HOST` / `APP_PORT` | Used if you wrap Uvicorn in your own launcher |

## API usage examples

### 1. Register and log in

```bash
curl -s -X POST http://127.0.0.1:8000/auth/register ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"you@example.com\",\"password\":\"your-secure-password\"}"

curl -s -X POST http://127.0.0.1:8000/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"you@example.com\",\"password\":\"your-secure-password\"}"
```

Copy `access_token` from the login response.

### 2. Protected routes

Send the header on trip and itinerary routes:

`Authorization: Bearer <access_token>`

```bash
curl -s http://127.0.0.1:8000/users/me -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 3. Trips

```bash
curl -s -X POST http://127.0.0.1:8000/trips ^
  -H "Authorization: Bearer YOUR_TOKEN_HERE" ^
  -H "Content-Type: application/json" ^
  -d "{\"destination\":\"Paris\",\"days\":5,\"budget\":1500,\"trip_style\":\"budget\"}"

curl -s http://127.0.0.1:8000/trips -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

`POST /trips` responses include **`message`: `"Trip created successfully"`** (same idea as the course examples). List and single-trip `GET` responses return trip fields only (no `message`).

### 4. Itineraries

```bash
curl -s -X POST http://127.0.0.1:8000/itineraries ^
  -H "Authorization: Bearer YOUR_TOKEN_HERE" ^
  -H "Content-Type: application/json" ^
  -d "{\"trip_id\":1,\"days\":[{\"day\":1,\"activities\":[\"Eiffel Tower\"]}]}"

curl -s http://127.0.0.1:8000/itineraries/1 -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

On Unix, replace `^` line continuations with `\`.

## Response shapes (course brief)

Successful **`POST /trips`** body:

```json
{
  "id": 1,
  "destination": "Paris",
  "days": 5,
  "budget": 1500,
  "trip_style": "budget",
  "message": "Trip created successfully"
}
```

Successful **`POST /itineraries`** body:

```json
{
  "trip_id": 1,
  "itinerary": [
    { "day": 1, "activities": ["Eiffel Tower", "Seine River Walk"] },
    { "day": 2, "activities": ["Louvre Museum", "Montmartre"] }
  ],
  "message": "Itinerary created successfully"
}
```

Successful **`GET /itineraries/{trip_id}`** body: same `trip_id` and `itinerary` array, without `message`.

## Error responses

- **4xx/5xx from `HTTPException`:** JSON body `{"detail": "<string>"}`.
- **422 validation:** JSON body `{"detail": [<object>, ...]}` where each object includes `loc`, `msg`, and `type` (FastAPI / Pydantic default).

## OpenAPI

Tags group **Health**, **Auth**, **Users**, **Trips**, **Itineraries**. Prefer `/docs` for interactive calls and schema export.
