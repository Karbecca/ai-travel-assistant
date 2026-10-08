import importlib

from fastapi.testclient import TestClient


def _reload_app() -> object:
    from app.core.config import get_settings

    get_settings.cache_clear()

    import app.core.database as database_module
    import app.deps as deps_module
    import app.main as main_module
    import app.models.trip as trip_module
    import app.models.user as user_module
    import app.routers.auth as auth_module
    import app.routers.trips as trips_module
    import app.routers.users as users_module

    importlib.reload(database_module)
    importlib.reload(user_module)
    importlib.reload(trip_module)
    importlib.reload(deps_module)
    importlib.reload(auth_module)
    importlib.reload(trips_module)
    importlib.reload(users_module)
    importlib.reload(main_module)

    return main_module.app


def _register_and_login(client: TestClient, email: str) -> str:
    client.post("/auth/register", json={"email": email, "password": "password123"})
    response = client.post("/auth/login", json={"email": email, "password": "password123"})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_trip_crud_happy_path(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "trips.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = _reload_app()

    with TestClient(app) as client:
        token = _register_and_login(client, "tripper@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        create_response = client.post(
            "/trips",
            json={
                "destination": "Paris",
                "days": 5,
                "budget": 1500,
                "trip_style": "budget",
            },
            headers=headers,
        )
        assert create_response.status_code == 200
        created_trip = create_response.json()
        trip_id = created_trip["id"]
        assert created_trip["destination"] == "Paris"
        assert created_trip["message"] == "Trip created successfully"

        list_response = client.get("/trips", headers=headers)
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1

        get_response = client.get(f"/trips/{trip_id}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["trip_style"] == "budget"

        update_response = client.put(
            f"/trips/{trip_id}",
            json={"budget": 1800, "trip_style": "midrange"},
            headers=headers,
        )
        assert update_response.status_code == 200
        assert update_response.json()["budget"] == 1800
        assert update_response.json()["trip_style"] == "midrange"

        delete_response = client.delete(f"/trips/{trip_id}", headers=headers)
        assert delete_response.status_code == 204

        after_delete = client.get(f"/trips/{trip_id}", headers=headers)
        assert after_delete.status_code == 404


def test_trip_routes_enforce_auth_and_ownership(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "trips_authz.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")

    app = _reload_app()

    with TestClient(app) as client:
        owner_token = _register_and_login(client, "owner@example.com")
        attacker_token = _register_and_login(client, "attacker@example.com")

        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        attacker_headers = {"Authorization": f"Bearer {attacker_token}"}

        create_response = client.post(
            "/trips",
            json={
                "destination": "Rome",
                "days": 3,
                "budget": 900,
                "trip_style": "relaxed",
            },
            headers=owner_headers,
        )
        trip_id = create_response.json()["id"]

        unauth_list = client.get("/trips")
        assert unauth_list.status_code == 401

        forbidden_get = client.get(f"/trips/{trip_id}", headers=attacker_headers)
        assert forbidden_get.status_code == 404

        forbidden_update = client.put(
            f"/trips/{trip_id}",
            json={"days": 4},
            headers=attacker_headers,
        )
        assert forbidden_update.status_code == 404

        forbidden_delete = client.delete(f"/trips/{trip_id}", headers=attacker_headers)
        assert forbidden_delete.status_code == 404
