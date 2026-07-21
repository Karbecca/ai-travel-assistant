import json
import re

from anthropic import Anthropic

from app.core.config import get_settings
from app.services.weather import WeatherServiceError, get_current_weather

SYSTEM_PROMPT = """You are a travel itinerary planner.
Return ONLY valid JSON with this exact shape:
{"days": [{"day": 1, "activities": ["activity 1", "activity 2"]}, ...]}
Rules:
- Match the exact number of days specified in the user message
- Number days from 1 through N with no gaps or duplicates
- Every activity must be located in or very near the destination area only
- Respect the stated budget and travel style when choosing activities
- Suggest 3 to 6 realistic activities per day appropriate to the travel style
- Do not include prices, booking links, or any text outside the JSON object"""

_WEATHER_TOOL = {
    "name": "get_current_weather",
    "description": "Fetch current weather at the destination to inform activity planning.",
    "input_schema": {
        "type": "object",
        "properties": {
            "destination": {
                "type": "string",
                "description": "City or region name",
            }
        },
        "required": ["destination"],
    },
}


class LLMConfigurationError(Exception):
    pass


class LLMResponseError(Exception):
    pass


def build_user_prompt(*, destination: str, days: int, budget: float, trip_style: str) -> str:
    return f"""Plan a {days}-day trip to {destination} with a budget of {budget}.
The travel style is {trip_style}.
Include only places and experiences within {destination} or its immediate surroundings.
Spread activities across all {days} days and keep suggestions realistic for the budget and style.
Return exactly {days} day entries in the JSON days array."""


def _extract_json_text(raw: str) -> str:
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence_match:
        return fence_match.group(1).strip()
    return text


def _parse_days_payload(raw: str, expected_days: int) -> list[dict[str, object]]:
    try:
        data = json.loads(_extract_json_text(raw))
    except json.JSONDecodeError as exc:
        raise LLMResponseError("LLM returned invalid JSON") from exc

    if not isinstance(data, dict) or "days" not in data:
        raise LLMResponseError("LLM response missing days array")

    days_list = data["days"]
    if not isinstance(days_list, list):
        raise LLMResponseError("LLM days field is not a list")

    if len(days_list) != expected_days:
        raise LLMResponseError(f"LLM returned {len(days_list)} days, expected {expected_days}")

    normalized: list[dict[str, object]] = []
    seen_days: set[int] = set()

    for entry in days_list:
        if not isinstance(entry, dict):
            raise LLMResponseError("Each day entry must be an object")
        if "day" not in entry or "activities" not in entry:
            raise LLMResponseError("Each day entry must include day and activities")
        day_number = entry["day"]
        activities = entry["activities"]
        if not isinstance(day_number, int) or day_number < 1:
            raise LLMResponseError("Each day number must be a positive integer")
        if day_number in seen_days:
            raise LLMResponseError("Duplicate day numbers in LLM response")
        if not isinstance(activities, list) or not all(isinstance(a, str) for a in activities):
            raise LLMResponseError("Activities must be a list of strings")
        seen_days.add(day_number)
        normalized.append({"day": day_number, "activities": list(activities)})

    if seen_days != set(range(1, expected_days + 1)):
        raise LLMResponseError("LLM day numbers must be consecutive from 1 to N")

    normalized.sort(key=lambda row: row["day"])
    return normalized


def _handle_tool_call(name: str, tool_input: dict) -> str:
    if name == "get_current_weather":
        try:
            result = get_current_weather(tool_input["destination"])
        except WeatherServiceError as exc:
            result = {"error": str(exc)}
        return json.dumps(result)
    return json.dumps({"error": f"Unknown tool: {name}"})


def _call_llm(client: Anthropic, settings, user_prompt: str) -> str:
    tools = [_WEATHER_TOOL] if settings.weather_api_key else []

    base_kwargs: dict = {
        "model": settings.anthropic_model,
        "max_tokens": settings.anthropic_max_tokens,
        "temperature": settings.anthropic_temperature,
        "system": SYSTEM_PROMPT,
    }
    if tools:
        base_kwargs["tools"] = tools

    messages: list = [{"role": "user", "content": user_prompt}]

    while True:
        response = client.messages.create(**base_kwargs, messages=messages)

        if response.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _handle_tool_call(block.name, block.input),
                }
                for block in response.content
                if block.type == "tool_use"
            ],
        })

    content = next((block.text for block in response.content if block.type == "text"), None)
    if not content:
        raise LLMResponseError("LLM returned empty response")
    return content


def generate_itinerary_days(
    *,
    destination: str,
    days: int,
    budget: float,
    trip_style: str,
) -> list[dict[str, object]]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise LLMConfigurationError("LLM service not configured")

    client = Anthropic(api_key=settings.anthropic_api_key)
    user_prompt = build_user_prompt(
        destination=destination,
        days=days,
        budget=budget,
        trip_style=trip_style,
    )

    last_exc: LLMResponseError | None = None

    for _ in range(settings.llm_max_retries + 1):
        try:
            raw = _call_llm(client, settings, user_prompt)
        except Exception as exc:
            raise LLMResponseError("LLM service request failed") from exc

        try:
            return _parse_days_payload(raw, expected_days=days)
        except LLMResponseError as exc:
            last_exc = exc

    if last_exc is not None:
        raise last_exc
    raise LLMResponseError("LLM failed to return a valid response")
