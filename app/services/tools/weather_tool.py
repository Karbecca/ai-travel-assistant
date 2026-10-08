from langchain_core.tools import tool

from app.services.weather import WeatherServiceError, get_current_weather


@tool
def weather_tool(destination: str) -> str:
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
