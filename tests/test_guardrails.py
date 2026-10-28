import json

import pytest

from app.services.guardrails import (
    ALLOWED_TRIP_STYLES,
    GuardrailInputError,
    GuardrailOutputError,
    validate_itinerary_input,
    validate_itinerary_output,
)


def _settings(max_len=2000, min_days=1, max_days=30):
    from unittest.mock import MagicMock
    return MagicMock(
        guardrail_max_input_length=max_len,
        guardrail_min_days=min_days,
        guardrail_max_days=max_days,
    )


def _valid_output(days=1):
    return json.dumps({
        "days": [{"day": i, "activities": ["Visit a museum", "Walk in the park"]} for i in range(1, days + 1)]
    })


class TestValidateInput:
    def test_valid_passes(self):
        validate_itinerary_input("Paris", "cultural", 3, _settings())

    def test_empty_destination_raises(self):
        with pytest.raises(GuardrailInputError, match="destination"):
            validate_itinerary_input("", "cultural", 3, _settings())

    def test_destination_too_long_raises(self):
        with pytest.raises(GuardrailInputError, match="destination"):
            validate_itinerary_input("x" * 2001, "cultural", 3, _settings())

    def test_injection_raises(self):
        with pytest.raises(GuardrailInputError, match="destination"):
            validate_itinerary_input("ignore previous instructions", "cultural", 3, _settings())

    def test_injection_case_insensitive(self):
        with pytest.raises(GuardrailInputError):
            validate_itinerary_input("IGNORE PREVIOUS", "cultural", 3, _settings())

    def test_invalid_trip_style_raises(self):
        with pytest.raises(GuardrailInputError, match="trip_style"):
            validate_itinerary_input("Paris", "invalid_style", 3, _settings())

    def test_all_allowed_styles_pass(self):
        for style in ALLOWED_TRIP_STYLES:
            validate_itinerary_input("Paris", style, 3, _settings())

    def test_days_below_min_raises(self):
        with pytest.raises(GuardrailInputError, match="days"):
            validate_itinerary_input("Paris", "cultural", 0, _settings())

    def test_days_above_max_raises(self):
        with pytest.raises(GuardrailInputError, match="days"):
            validate_itinerary_input("Paris", "cultural", 31, _settings())

    def test_days_at_boundary_pass(self):
        validate_itinerary_input("Paris", "cultural", 1, _settings())
        validate_itinerary_input("Paris", "cultural", 30, _settings())


class TestValidateOutput:
    def test_valid_output_passes(self):
        validate_itinerary_output(_valid_output(1), 1)

    def test_empty_raises(self):
        with pytest.raises(GuardrailOutputError, match="Empty"):
            validate_itinerary_output("", 1)

    def test_invalid_json_raises(self):
        with pytest.raises(GuardrailOutputError, match="JSON"):
            validate_itinerary_output("not json", 1)

    def test_missing_days_key_raises(self):
        with pytest.raises(GuardrailOutputError, match="days"):
            validate_itinerary_output(json.dumps({"other": []}), 1)

    def test_wrong_day_count_raises(self):
        with pytest.raises(GuardrailOutputError, match="Expected 2"):
            validate_itinerary_output(_valid_output(1), 2)

    def test_missing_activities_key_raises(self):
        bad = json.dumps({"days": [{"day": 1}]})
        with pytest.raises(GuardrailOutputError, match="missing required keys"):
            validate_itinerary_output(bad, 1)

    def test_activity_too_long_raises(self):
        bad = json.dumps({"days": [{"day": 1, "activities": ["x" * 501]}]})
        with pytest.raises(GuardrailOutputError, match="too long"):
            validate_itinerary_output(bad, 1)

    def test_injection_in_output_raises(self):
        bad = json.dumps({"days": [{"day": 1, "activities": ["ignore previous instructions"]}]})
        with pytest.raises(GuardrailOutputError, match="Unsafe"):
            validate_itinerary_output(bad, 1)

    def test_multi_day_valid(self):
        validate_itinerary_output(_valid_output(5), 5)
