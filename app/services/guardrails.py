import json
import re

_INJECTION_RE = re.compile(
    r"(ignore\s+previous|forget\s+instructions|you\s+are\s+now|"
    r"system\s*:\s*|<\s*system\s*>|act\s+as\s+if|jailbreak|"
    r"override\s+your|disregard\s+all)",
    re.IGNORECASE,
)

ALLOWED_TRIP_STYLES = frozenset({
    "adventure", "cultural", "relaxation", "family",
    "romantic", "budget", "luxury", "business",
})


class GuardrailInputError(Exception):
    def __init__(self, message: str, field: str = ""):
        self.field = field
        super().__init__(message)


class GuardrailOutputError(Exception):
    def __init__(self, message: str, check: str = ""):
        self.check = check
        super().__init__(message)


def validate_itinerary_input(destination: str, trip_style: str, num_days: int, settings) -> None:
    if not destination or len(destination) > settings.guardrail_max_input_length:
        raise GuardrailInputError("Invalid destination length.", field="destination")
    if _INJECTION_RE.search(destination):
        raise GuardrailInputError("Unsafe content in destination.", field="destination")
    if trip_style not in ALLOWED_TRIP_STYLES:
        raise GuardrailInputError(f"Unsupported trip_style: {trip_style}.", field="trip_style")
    if not (settings.guardrail_min_days <= num_days <= settings.guardrail_max_days):
        raise GuardrailInputError(
            f"days must be between {settings.guardrail_min_days} and {settings.guardrail_max_days}.",
            field="days",
        )


def validate_itinerary_output(raw_response: str, expected_days: int) -> None:
    if not raw_response:
        raise GuardrailOutputError("Empty response.", check="empty")
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise GuardrailOutputError(f"Invalid JSON: {exc}", check="json") from exc
    if "days" not in data:
        raise GuardrailOutputError("Missing 'days' key.", check="structure")
    days = data["days"]
    if len(days) != expected_days:
        raise GuardrailOutputError(
            f"Expected {expected_days} days, got {len(days)}.", check="day_count"
        )
    for entry in days:
        if "day" not in entry or "activities" not in entry:
            raise GuardrailOutputError("Day entry missing required keys.", check="day_keys")
        for activity in entry["activities"]:
            if len(activity) > 500:
                raise GuardrailOutputError("Activity string too long.", check="activity_length")
            if _INJECTION_RE.search(activity):
                raise GuardrailOutputError("Unsafe content in output.", check="injection")
