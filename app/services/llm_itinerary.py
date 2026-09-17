import json
import re

from app.core.config import get_settings
from app.services.agent import AgentInput, run_travel_agent


class LLMConfigurationError(Exception):
    pass


class LLMResponseError(Exception):
    pass


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


def generate_itinerary_days(
    *, destination: str, days: int, budget: float, trip_style: str
) -> list[dict]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise LLMConfigurationError("LLM service not configured")

    agent_input: AgentInput = {
        "destination": destination,
        "days": days,
        "budget": budget,
        "trip_style": trip_style,
    }

    last_exc: LLMResponseError | None = None
    for _ in range(settings.llm_max_retries + 1):
        try:
            raw = run_travel_agent(agent_input)
        except Exception as exc:
            raise LLMResponseError("LLM service request failed") from exc
        try:
            return _parse_days(raw, expected=days)
        except LLMResponseError as exc:
            last_exc = exc

    if last_exc is not None:
        raise last_exc
    raise LLMResponseError("LLM failed to return a valid response")
