import json
import re

from anthropic import Anthropic

from app.core.config import get_settings
from app.services import knowledge_base
from app.services.weather import WeatherServiceError, get_current_weather

_BASE_SYSTEM_PROMPT = """You are a travel itinerary planner.
Return ONLY valid JSON with this exact shape:
{"days": [{"day": 1, "activities": ["activity 1", "activity 2"]}, ...]}
Rules:
- Match the exact number of days specified in the user message
- Number days from 1 through N with no gaps or duplicates
- Every activity must be located in or very near the destination
- Respect the stated budget and travel style when choosing activities
- Suggest 3 to 6 realistic activities per day
- Do not include prices, booking links, or any text outside the JSON
"""


def _build_system_prompt(destination: str) -> str:
    """Augment the base system prompt with retrieved knowledge base context."""
    try:
        hits = knowledge_base.search(destination, n_results=3, destination_filter="")
    except Exception:
        hits = []

    if not hits:
        return _BASE_SYSTEM_PROMPT

    context_lines = "\n".join(
        f"- [{h['title']}] {h['content']}" for h in hits
    )
    return (
        _BASE_SYSTEM_PROMPT
        + f"\n### Local Knowledge\nUse the following curated travel information "
        f"about {destination} when choosing activities:\n{context_lines}\n"
    )

_WEATHER_TOOL = {
    "name": "get_current_weather",
    "description": "Fetch current weather at the destination to inform activity planning.",
    "input_schema": {
        "type": "object",
        "properties": {"destination": {"type": "string"}},
        "required": ["destination"],
    },
}


class LLMConfigurationError(Exception):
    pass


class LLMResponseError(Exception):
    pass


def build_user_prompt(
    *, destination: str, days: int, budget: float, trip_style: str
) -> str:
    return (
        f"Plan a {days}-day trip to {destination} with a budget of {budget}.\n"
        f"The travel style is {trip_style}.\n"
        f"Include only places in {destination} or its immediate surroundings.\n"
        f"Return exactly {days} day entries in the JSON days array."
    )


def _extract_json(raw: str) -> str:
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw.strip())
    return m.group(1).strip() if m else raw.strip()


def _parse_days(raw: str, expected: int) -> list[dict]:
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError as exc:
        raise LLMResponseError("LLM returned invalid JSON") from exc

    days = data.get("days") if isinstance(data, dict) else None
    if not isinstance(days, list) or len(days) != expected:
        raise LLMResponseError(f"Expected {expected}-item days array")

    seen, out = set(), []
    for entry in days:
        if not isinstance(entry, dict) or "day" not in entry or "activities" not in entry:
            raise LLMResponseError("Each day entry must include day and activities")
        d, acts = entry["day"], entry["activities"]
        if not isinstance(d, int) or d < 1 or d in seen:
            raise LLMResponseError("Invalid or duplicate day number")
        if not isinstance(acts, list) or not all(isinstance(a, str) for a in acts):
            raise LLMResponseError("Activities must be a list of strings")
        seen.add(d)
        out.append({"day": d, "activities": list(acts)})

    if seen != set(range(1, expected + 1)):
        raise LLMResponseError("Day numbers must be consecutive from 1 to N")
    return sorted(out, key=lambda r: r["day"])


def _handle_tool(block) -> dict:
    try:
        return get_current_weather(block.input["destination"])
    except WeatherServiceError as exc:
        return {"error": str(exc)}


def _call_llm(client: Anthropic, settings, user_prompt: str, system_prompt: str) -> str:
    tools = [_WEATHER_TOOL] if settings.weather_api_key else []
    kw = {
        "model": settings.anthropic_model,
        "max_tokens": settings.anthropic_max_tokens,
        "temperature": settings.anthropic_temperature,
        "system": system_prompt,
    }
    if tools:
        kw["tools"] = tools

    msgs = [{"role": "user", "content": user_prompt}]
    while True:
        response = client.messages.create(**kw, messages=msgs)
        if response.stop_reason != "tool_use":
            break
        msgs.append({"role": "assistant", "content": response.content})
        msgs.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": json.dumps(_handle_tool(b)),
                }
                for b in response.content if b.type == "tool_use"
            ],
        })

    content = next((b.text for b in response.content if b.type == "text"), None)
    if not content:
        raise LLMResponseError("LLM returned empty response")
    return content


def generate_itinerary_days(
    *, destination: str, days: int, budget: float, trip_style: str
) -> list[dict]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise LLMConfigurationError("LLM service not configured")

    client = Anthropic(api_key=settings.anthropic_api_key)
    system_prompt = _build_system_prompt(destination)
    user_prompt = build_user_prompt(
        destination=destination, days=days, budget=budget, trip_style=trip_style
    )

    last_exc: LLMResponseError | None = None
    for _ in range(settings.llm_max_retries + 1):
        try:
            raw = _call_llm(client, settings, user_prompt, system_prompt)
        except Exception as exc:
            raise LLMResponseError("LLM service request failed") from exc
        try:
            return _parse_days(raw, expected=days)
        except LLMResponseError as exc:
            last_exc = exc

    if last_exc is not None:
        raise last_exc
    raise LLMResponseError("LLM failed to return a valid response")
