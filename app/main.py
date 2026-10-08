from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import Base, engine
from app.routers.auth import router as auth_router
from app.routers.health import router as health_router
from app.routers.itineraries import router as itineraries_router
from app.routers.knowledge import router as knowledge_router
from app.routers.trips import router as trips_router
from app.routers.users import router as users_router

settings = get_settings()

_OPENAPI_TAGS = [
    {"name": "Health", "description": "Liveness for monitoring and local smoke checks."},
    {"name": "Auth", "description": "Register and obtain a JWT access token."},
    {"name": "Users", "description": "Authenticated user profile."},
    {"name": "Trips", "description": "CRUD for trips owned by the current user."},
    {"name": "Itineraries", "description": "Create and fetch itineraries linked to a trip."},
    {"name": "Knowledge", "description": "Travel knowledge base: add documents and run semantic search."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    import app.models.itinerary  # noqa: F401
    import app.models.trip  # noqa: F401
    import app.models.user  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "REST API for trip planning: JWT auth, trips, itineraries, and audit hooks after writes."
    ),
    version="0.1.0",
    lifespan=lifespan,
    openapi_tags=_OPENAPI_TAGS,
)

app.include_router(health_router)
app.include_router(auth_router, prefix="/auth")
app.include_router(users_router, prefix="/users")
app.include_router(trips_router, prefix="/trips")
app.include_router(itineraries_router, prefix="/itineraries")
app.include_router(knowledge_router, prefix="/knowledge")
