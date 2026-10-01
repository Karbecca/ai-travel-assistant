from unittest.mock import patch

import pytest

import app.services.llm_itinerary as llm

_VALID_JSON = '{"days": [{"day": 1, "activities": ["Eiffel Tower", "Seine walk"]}]}'
_INVALID_JSON = "not valid json"


def _mock_settings(**overrides):
    from unittest.mock import MagicMock
    defaults = {
        "anthropic_api_key": "test-key",
        "llm_max_retries": 2,
    }
    return MagicMock(**{**defaults, **overrides})


def test_raises_configuration_error_when_no_api_key():
    with patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(anthropic_api_key="")
        with pytest.raises(llm.LLMConfigurationError):
            llm.generate_itinerary_days(
                destination="Paris", days=1, budget=1000.0, trip_style="budget"
            )


def test_retries_on_parse_failure():
    with patch("app.services.llm_itinerary.run_travel_agent") as mock_agent, \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(llm_max_retries=2)
        mock_agent.side_effect = [_INVALID_JSON, _VALID_JSON]

        result = llm.generate_itinerary_days(
            destination="Paris", days=1, budget=1000.0, trip_style="budget"
        )

    assert len(result) == 1
    assert mock_agent.call_count == 2


def test_raises_after_all_retries_exhausted():
    with patch("app.services.llm_itinerary.run_travel_agent") as mock_agent, \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(llm_max_retries=2)
        mock_agent.return_value = _INVALID_JSON

        with pytest.raises(llm.LLMResponseError):
            llm.generate_itinerary_days(
                destination="Paris", days=1, budget=1000.0, trip_style="budget"
            )

    assert mock_agent.call_count == 3


def test_returns_parsed_days_on_valid_response():
    with patch("app.services.llm_itinerary.run_travel_agent") as mock_agent, \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(llm_max_retries=0)
        mock_agent.return_value = _VALID_JSON

        result = llm.generate_itinerary_days(
            destination="Paris", days=1, budget=1000.0, trip_style="budget"
        )

    assert result == [{"day": 1, "activities": ["Eiffel Tower", "Seine walk"]}]


def test_agent_called_with_correct_input():
    with patch("app.services.llm_itinerary.run_travel_agent") as mock_agent, \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(llm_max_retries=0)
        mock_agent.return_value = _VALID_JSON

        llm.generate_itinerary_days(
            destination="Paris", days=1, budget=500.0, trip_style="adventure"
        )

    called_input = mock_agent.call_args[0][0]
    assert called_input["destination"] == "Paris"
    assert called_input["days"] == 1
    assert called_input["budget"] == 500.0
    assert called_input["trip_style"] == "adventure"


def test_agent_exception_raises_llm_response_error():
    with patch("app.services.llm_itinerary.run_travel_agent") as mock_agent, \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(llm_max_retries=0)
        mock_agent.side_effect = RuntimeError("network error")

        with pytest.raises(llm.LLMResponseError, match="LLM service request failed"):
            llm.generate_itinerary_days(
                destination="Paris", days=1, budget=1000.0, trip_style="budget"
            )
