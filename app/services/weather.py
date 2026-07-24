import httpx

from app.core.config import get_settings

_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


class WeatherServiceError(Exception):
    pass


def get_current_weather(destination: str) -> dict[str, object]:
    settings = get_settings()
    if not settings.weather_api_key:
        raise WeatherServiceError("Weather service not configured")

    try:
        response = httpx.get(
            _WEATHER_URL,
            params={"q": destination, "appid": settings.weather_api_key, "units": "metric"},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise WeatherServiceError(f"Weather API error: {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise WeatherServiceError("Weather API request failed") from exc

    data = response.json()
    return {
        "temperature_celsius": data["main"]["temp"],
        "description": data["weather"][0]["description"],
        "humidity_percent": data["main"]["humidity"],
    }
