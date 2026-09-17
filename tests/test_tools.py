from unittest.mock import MagicMock, patch

from app.services.tools.knowledge_tool import knowledge_tool
from app.services.tools.places_tool import places_tool
from app.services.tools.pricing_tool import pricing_tool
from app.services.tools.weather_tool import weather_tool


# --- weather tool ---

def test_weather_tool_returns_formatted_string():
    weather_data = {
        "temperature_celsius": 18.0,
        "description": "clear sky",
        "humidity_percent": 55,
    }
    with patch("app.services.tools.weather_tool.get_current_weather", return_value=weather_data):
        result = weather_tool.invoke({"destination": "Paris"})

    assert "Paris" in result
    assert "18.0" in result
    assert "clear sky" in result


def test_weather_tool_handles_service_error():
    from app.services.weather import WeatherServiceError
    with patch("app.services.tools.weather_tool.get_current_weather",
               side_effect=WeatherServiceError("API down")):
        result = weather_tool.invoke({"destination": "Paris"})

    assert "unavailable" in result.lower()


# --- knowledge tool ---

def test_knowledge_tool_returns_hits():
    hits = [
        {"title": "Paris tips", "content": "Visit Le Marais."},
        {"title": "Paris food", "content": "Try croissants."},
    ]
    with patch("app.services.tools.knowledge_tool.knowledge_base.search", return_value=hits):
        result = knowledge_tool.invoke({"query": "Paris"})

    assert "Paris tips" in result
    assert "Le Marais" in result


def test_knowledge_tool_no_results():
    with patch("app.services.tools.knowledge_tool.knowledge_base.search", return_value=[]):
        result = knowledge_tool.invoke({"query": "nowhere"})

    assert "No relevant" in result


def test_knowledge_tool_handles_exception():
    with patch("app.services.tools.knowledge_tool.knowledge_base.search",
               side_effect=Exception("KB down")):
        result = knowledge_tool.invoke({"query": "Paris"})

    assert "unavailable" in result.lower()


# --- pricing tool ---

def test_pricing_tool_known_city():
    result = pricing_tool.invoke({"destination": "Paris", "days": 5, "budget": 1500.0})
    assert "Paris" in result
    assert "300" in result  # 1500/5 = 300/day
    assert any(tier in result for tier in ["comfortable", "moderate", "budget-friendly", "tight"])


def test_pricing_tool_tight_budget():
    result = pricing_tool.invoke({"destination": "Paris", "days": 10, "budget": 200.0})
    assert "tight" in result


def test_pricing_tool_comfortable_budget():
    result = pricing_tool.invoke({"destination": "Paris", "days": 5, "budget": 5000.0})
    assert "comfortable" in result


def test_pricing_tool_unknown_city_defaults_to_western_europe():
    result = pricing_tool.invoke({"destination": "Atlantis", "days": 3, "budget": 600.0})
    assert "Atlantis" in result
    assert "$120" in result or "$200" in result or "western europe" in result.lower()


# --- places tool ---

def test_places_tool_no_api_key():
    with patch("app.services.tools.places_tool.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(opentripmap_api_key="")
        result = places_tool.invoke({"destination": "Paris"})

    assert "not configured" in result.lower()


def test_places_tool_returns_places():
    geo_response = MagicMock()
    geo_response.json.return_value = {"lat": 48.8566, "lon": 2.3522}
    geo_response.raise_for_status = MagicMock()

    radius_response = MagicMock()
    radius_response.json.return_value = {
        "features": [
            {"properties": {"name": "Eiffel Tower"}},
            {"properties": {"name": "Louvre Museum"}},
        ]
    }
    radius_response.raise_for_status = MagicMock()

    with patch("app.services.tools.places_tool.get_settings") as mock_settings, \
         patch("app.services.tools.places_tool.httpx.get") as mock_get:
        mock_settings.return_value = MagicMock(opentripmap_api_key="test-key")
        mock_get.side_effect = [geo_response, radius_response]

        result = places_tool.invoke({"destination": "Paris"})

    assert "Eiffel Tower" in result
    assert "Louvre Museum" in result


def test_places_tool_handles_http_error():
    import httpx
    with patch("app.services.tools.places_tool.get_settings") as mock_settings, \
         patch("app.services.tools.places_tool.httpx.get",
               side_effect=httpx.HTTPError("timeout")):
        mock_settings.return_value = MagicMock(opentripmap_api_key="test-key")
        result = places_tool.invoke({"destination": "Paris"})

    assert "failed" in result.lower()
