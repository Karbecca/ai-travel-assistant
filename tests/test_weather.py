from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.weather import WeatherServiceError, get_current_weather


def test_raises_when_no_api_key():
    with patch("app.services.weather.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(weather_api_key="")
        with pytest.raises(WeatherServiceError, match="not configured"):
            get_current_weather("Paris")


def test_raises_on_http_status_error():
    with patch("app.services.weather.get_settings") as mock_settings, \
         patch("app.services.weather.httpx.get") as mock_get:
        mock_settings.return_value = MagicMock(weather_api_key="test-key")
        mock_response = MagicMock(status_code=401)
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401", request=MagicMock(), response=mock_response
        )
        mock_get.return_value = mock_response

        with pytest.raises(WeatherServiceError, match="401"):
            get_current_weather("Paris")


def test_raises_on_network_error():
    with patch("app.services.weather.get_settings") as mock_settings, \
         patch("app.services.weather.httpx.get") as mock_get:
        mock_settings.return_value = MagicMock(weather_api_key="test-key")
        mock_get.side_effect = httpx.ConnectError("connection refused")

        with pytest.raises(WeatherServiceError, match="request failed"):
            get_current_weather("Paris")


def test_returns_weather_data_on_success():
    api_payload = {
        "main": {"temp": 22.5, "humidity": 60},
        "weather": [{"description": "clear sky"}],
    }
    with patch("app.services.weather.get_settings") as mock_settings, \
         patch("app.services.weather.httpx.get") as mock_get:
        mock_settings.return_value = MagicMock(weather_api_key="test-key")
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = api_payload
        mock_get.return_value = mock_response

        result = get_current_weather("Paris")

    assert result == {
        "temperature_celsius": 22.5,
        "description": "clear sky",
        "humidity_percent": 60,
    }
    mock_get.assert_called_once_with(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"q": "Paris", "appid": "test-key", "units": "metric"},
        timeout=10.0,
    )
