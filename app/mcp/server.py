import httpx
from mcp.server.fastmcp import FastMCP

from app.core.config import get_settings
from app.services.weather import WeatherServiceError, get_current_weather

mcp = FastMCP("travel-tools")

_PLACES_BASE = "https://api.opentripmap.com/0.1/en/places"


@mcp.tool()
def get_weather(destination: str) -> str:
    """Get current weather conditions at a travel destination."""
    try:
        data = get_current_weather(destination)
        return (
            f"Weather in {destination}: {data['description']}, "
            f"{data['temperature_celsius']}°C, "
            f"{data['humidity_percent']}% humidity."
        )
    except WeatherServiceError as exc:
        return f"Weather unavailable: {exc}"


@mcp.tool()
def get_places(destination: str) -> str:
    """Find tourist attractions and points of interest at a destination."""
    settings = get_settings()
    if not settings.opentripmap_api_key:
        return "Places service not configured."

    try:
        geo = httpx.get(
            f"{_PLACES_BASE}/geoname",
            params={"name": destination, "apikey": settings.opentripmap_api_key},
            timeout=10.0,
        )
        geo.raise_for_status()
        loc = geo.json()

        radius = httpx.get(
            f"{_PLACES_BASE}/radius",
            params={
                "radius": 10000,
                "lon": loc["lon"],
                "lat": loc["lat"],
                "kinds": "interesting_places,tourist_facilities",
                "rate": "3",
                "limit": 8,
                "apikey": settings.opentripmap_api_key,
            },
            timeout=10.0,
        )
        radius.raise_for_status()
        features = radius.json().get("features", [])
    except httpx.HTTPError as exc:
        return f"Places lookup failed: {exc}"

    if not features:
        return f"No notable places found near {destination}."

    names = [
        f["properties"].get("name", "")
        for f in features
        if f["properties"].get("name")
    ]
    return f"Notable places in {destination}: {', '.join(names[:8])}."


if __name__ == "__main__":
    mcp.run()
