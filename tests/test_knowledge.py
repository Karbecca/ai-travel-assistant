import importlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


def _make_app():
    from app.core.config import get_settings
    get_settings.cache_clear()

    import app.core.database as db_mod
    import app.deps as deps_mod
    import app.main as main_mod
    import app.models.itinerary as itin_mod
    import app.models.trip as trip_mod
    import app.models.user as user_mod
    import app.routers.auth as auth_mod
    import app.routers.itineraries as itineraries_mod
    import app.routers.knowledge as knowledge_mod
    import app.routers.trips as trips_mod
    import app.routers.users as users_mod

    for mod in (db_mod, user_mod, trip_mod, itin_mod, deps_mod,
                auth_mod, trips_mod, itineraries_mod, users_mod,
                knowledge_mod, main_mod):
        importlib.reload(mod)

    return main_mod.app


@pytest.fixture()
def client_with_ephemeral_kb(tmp_path, monkeypatch):
    """TestClient with isolated SQLite DB and in-memory knowledge base."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'kb.sqlite').as_posix()}")

    app = _make_app()

    from app.services import knowledge_base
    knowledge_base.use_ephemeral_store()

    with TestClient(app) as client:
        yield client

    knowledge_base.use_ephemeral_store()


def _token(client: TestClient, email: str) -> str:
    client.post("/auth/register", json={"email": email, "password": "password123"})
    r = client.post("/auth/login", json={"email": email, "password": "password123"})
    return r.json()["access_token"]


def test_add_knowledge_entry(client_with_ephemeral_kb):
    client = client_with_ephemeral_kb
    headers = {"Authorization": f"Bearer {_token(client, 'kb_add@example.com')}"}

    response = client.post(
        "/knowledge",
        json={
            "title": "Hidden gems in Paris",
            "content": "Visit the covered passages like Galerie Vivienne.",
            "destination": "Paris",
            "category": "hidden gems",
        },
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Hidden gems in Paris"
    assert data["destination"] == "Paris"
    assert "id" in data


def test_add_requires_auth(client_with_ephemeral_kb):
    response = client_with_ephemeral_kb.post(
        "/knowledge",
        json={"title": "Test", "content": "Some content"},
    )
    assert response.status_code == 401


def test_search_returns_results(client_with_ephemeral_kb):
    client = client_with_ephemeral_kb
    headers = {"Authorization": f"Bearer {_token(client, 'kb_search@example.com')}"}

    client.post(
        "/knowledge",
        json={"title": "Paris tips", "content": "Best croissants in Le Marais.", "destination": "Paris"},
        headers=headers,
    )

    response = client.get("/knowledge/search?query=Paris+food", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "Paris food"
    assert isinstance(data["results"], list)
    assert len(data["results"]) >= 1
    assert data["results"][0]["title"] == "Paris tips"


def test_search_empty_kb_returns_empty(client_with_ephemeral_kb):
    client = client_with_ephemeral_kb
    headers = {"Authorization": f"Bearer {_token(client, 'kb_empty@example.com')}"}

    response = client.get("/knowledge/search?query=anywhere", headers=headers)
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_search_requires_auth(client_with_ephemeral_kb):
    response = client_with_ephemeral_kb.get("/knowledge/search?query=Paris")
    assert response.status_code == 401


def test_search_destination_filter(client_with_ephemeral_kb):
    client = client_with_ephemeral_kb
    headers = {"Authorization": f"Bearer {_token(client, 'kb_filter@example.com')}"}

    client.post(
        "/knowledge",
        json={"title": "Paris guide", "content": "Seine river walks.", "destination": "Paris"},
        headers=headers,
    )
    client.post(
        "/knowledge",
        json={"title": "Rome guide", "content": "Visit the Colosseum.", "destination": "Rome"},
        headers=headers,
    )

    response = client.get(
        "/knowledge/search?query=travel+guide&destination=Rome", headers=headers
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert all(r["destination"] == "Rome" for r in results)
