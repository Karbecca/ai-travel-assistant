import httpx
from langchain_core.tools import tool

from app.core.config import get_settings

_BASE = "https://api.opentripmap.com/0.1/en/places"


@tool
def places_tool(destination: str) -> str:
    """Find tourist attractions and points of interest at a destination."""
    settings = get_settings()
    if not settings.opentripmap_api_key:
        return "Places service not configured."

    try:
        geo = httpx.get(
            f"{_BASE}/geoname",
            params={"name": destination, "apikey": settings.opentripmap_api_key},
            timeout=10.0,
        )
        geo.raise_for_status()
        loc = geo.json()
        lat, lon = loc["lat"], loc["lon"]

        radius = httpx.get(
            f"{_BASE}/radius",
            params={
                "radius": 10000,
                "lon": lon,
                "lat": lat,
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

    names = [f["properties"].get("name", "Unnamed") for f in features if f["properties"].get("name")]
    return f"Notable places in {destination}: {', '.join(names[:8])}."
