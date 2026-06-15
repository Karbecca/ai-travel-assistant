import importlib
from unittest.mock import patch

from fastapi.testclient import TestClient


def _reload_app() -> object:
    from app.core.config import get_settings

    get_settings.cache_clear()

    import app.core.database as database_module
    import app.deps as deps_module
    import app.main as main_module
    import app.models.itinerary as itinerary_module
    import app.models.trip as trip_module
    import app.models.user as user_module
    import app.routers.auth as auth_module
    import app.routers.itineraries as itineraries_module
    import app.routers.trips as trips_module
    import app.routers.users as users_module
    import app.services.llm_itinerary as llm_itinerary_module

    importlib.reload(database_module)
    importlib.reload(llm_itinerary_module)
    importlib.reload(user_module)
    importlib.reload(trip_module)
    importlib.reload(itinerary_module)
    importlib.reload(deps_module)
    importlib.reload(auth_module)
    importlib.reload(trips_module)
    importlib.reload(itineraries_module)
    importlib.reload(users_module)
    importlib.reload(main_module)

    return main_module.app


def _register_and_login(client: TestClient, email: str) -> str:
    client.post("/auth/register", json={"email": email, "password": "password123"})
    response = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert response.status_code == 200
    return response.json()["access_token"]


def _create_trip(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post(
        "/trips",
        json={"destination": "Paris", "days": 5, "budget": 1500, "trip_style": "budget"},
        headers=headers,
    )
    assert response.status_code == 200
    return int(response.json()["id"])


def test_itinerary_create_and_get(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "itin.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = _reload_app()

    with TestClient(app) as client:
        token = _register_and_login(client, "planner@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        trip_id = _create_trip(client, headers)

        body = {
            "trip_id": trip_id,
            "days": [
                {"day": 2, "activities": ["Louvre"]},
                {"day": 1, "activities": ["Eiffel Tower", "Seine walk"]},
            ],
        }
        create = client.post("/itineraries", json=body, headers=headers)
        assert create.status_code == 200
        data = create.json()
        assert data["trip_id"] == trip_id
        assert data["message"] == "Itinerary created successfully"
        assert [d["day"] for d in data["itinerary"]] == [1, 2]
        assert data["itinerary"][1]["activities"] == ["Louvre"]

        fetched = client.get(f"/itineraries/{trip_id}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["itinerary"] == data["itinerary"]


def test_itinerary_post_updates_existing(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "itin_update.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = _reload_app()

    with TestClient(app) as client:
        token = _register_and_login(client, "planner2@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        trip_id = _create_trip(client, headers)

        first = client.post(
            "/itineraries",
            json={"trip_id": trip_id, "days": [{"day": 1, "activities": ["A"]}]},
            headers=headers,
        )
        assert first.status_code == 200

        second = client.post(
            "/itineraries",
            json={"trip_id": trip_id, "days": [{"day": 1, "activities": ["B"]}]},
            headers=headers,
        )
        assert second.status_code == 200
        assert second.json()["itinerary"][0]["activities"] == ["B"]


def test_itinerary_authz_and_not_found(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "itin_authz.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = _reload_app()

    with TestClient(app) as client:
        owner = _register_and_login(client, "owner_itin@example.com")
        other = _register_and_login(client, "other_itin@example.com")
        owner_headers = {"Authorization": f"Bearer {owner}"}
        other_headers = {"Authorization": f"Bearer {other}"}

        trip_id = _create_trip(client, owner_headers)

        assert client.get(f"/itineraries/{trip_id}", headers=other_headers).status_code == 404

        assert (
            client.post(
                "/itineraries",
                json={"trip_id": trip_id, "days": [{"day": 1, "activities": []}]},
                headers=other_headers,
            ).status_code
            == 404
        )

        assert client.get(f"/itineraries/{trip_id}", headers=owner_headers).status_code == 404

        assert client.post("/itineraries", json={"trip_id": 99999, "days": []}, headers=owner_headers).status_code == 404


def test_itinerary_generate_with_ai(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "itin_ai.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = _reload_app()

    with TestClient(app) as client:
        token = _register_and_login(client, "ai_planner@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        trip_id = _create_trip(client, headers)

        mock_days = [{"day": i, "activities": [f"Activity {i}a", f"Activity {i}b"]} for i in range(1, 6)]

        with patch("app.routers.itineraries.generate_itinerary_days", return_value=mock_days):
            response = client.post(
                "/itineraries",
                json={"trip_id": trip_id, "generate": True},
                headers=headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["trip_id"] == trip_id
        assert data["message"] == "Itinerary generated successfully"
        assert len(data["itinerary"]) == 5
        assert data["itinerary"][0]["activities"] == ["Activity 1a", "Activity 1b"]

        fetched = client.get(f"/itineraries/{trip_id}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["itinerary"] == data["itinerary"]


def test_itinerary_generate_rejects_days_with_generate_flag(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "itin_ai_invalid.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = _reload_app()

    with TestClient(app) as client:
        token = _register_and_login(client, "ai_invalid@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        trip_id = _create_trip(client, headers)

        response = client.post(
            "/itineraries",
            json={"trip_id": trip_id, "generate": True, "days": [{"day": 1, "activities": ["A"]}]},
            headers=headers,
        )
        assert response.status_code == 422


def test_itinerary_generate_missing_api_key(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "itin_ai_no_key.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    app = _reload_app()

    with TestClient(app) as client:
        token = _register_and_login(client, "ai_no_key@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        trip_id = _create_trip(client, headers)

        response = client.post(
            "/itineraries",
            json={"trip_id": trip_id, "generate": True},
            headers=headers,
        )
        assert response.status_code == 503


def test_itinerary_generate_llm_failure(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "itin_ai_fail.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = _reload_app()
    import app.services.llm_itinerary as llm_module

    with TestClient(app) as client:
        token = _register_and_login(client, "ai_fail@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        trip_id = _create_trip(client, headers)

        with patch(
            "app.routers.itineraries.generate_itinerary_days",
            side_effect=llm_module.LLMResponseError("LLM returned invalid JSON"),
        ):
            response = client.post(
                "/itineraries",
                json={"trip_id": trip_id, "generate": True},
                headers=headers,
            )

        assert response.status_code == 502
