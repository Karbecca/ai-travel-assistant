from unittest.mock import MagicMock, patch

import pytest

import app.services.llm_itinerary as llm

_VALID_JSON = '{"days": [{"day": 1, "activities": ["Eiffel Tower", "Seine walk"]}]}'
_INVALID_JSON = "not valid json"


def _text_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [block]
    return response


def _tool_use_response(tool_id: str, name: str, tool_input: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.id = tool_id
    block.name = name
    block.input = tool_input
    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [block]
    return response


def _mock_settings(**overrides) -> MagicMock:
    defaults = {
        "anthropic_api_key": "test-key",
        "weather_api_key": "",
        "anthropic_model": "claude-haiku-4-5-20251001",
        "anthropic_max_tokens": 2000,
        "anthropic_temperature": 0.7,
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
    with patch("app.services.llm_itinerary.Anthropic") as mock_cls, \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(llm_max_retries=2)
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            _text_response(_INVALID_JSON),
            _text_response(_VALID_JSON),
        ]

        result = llm.generate_itinerary_days(
            destination="Paris", days=1, budget=1000.0, trip_style="budget"
        )

    assert len(result) == 1
    assert mock_client.messages.create.call_count == 2


def test_raises_after_all_retries_exhausted():
    with patch("app.services.llm_itinerary.Anthropic") as mock_cls, \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(llm_max_retries=2)
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _text_response(_INVALID_JSON)

        with pytest.raises(llm.LLMResponseError):
            llm.generate_itinerary_days(
                destination="Paris", days=1, budget=1000.0, trip_style="budget"
            )

    assert mock_client.messages.create.call_count == 3


def test_weather_tool_included_when_api_key_set():
    with patch("app.services.llm_itinerary.Anthropic") as mock_cls, \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(weather_api_key="weather-key", llm_max_retries=0)
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _text_response(_VALID_JSON)

        llm.generate_itinerary_days(
            destination="Paris", days=1, budget=1000.0, trip_style="budget"
        )

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "tools" in call_kwargs
    assert call_kwargs["tools"][0]["name"] == "get_current_weather"


def test_weather_tool_excluded_when_no_api_key():
    with patch("app.services.llm_itinerary.Anthropic") as mock_cls, \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(weather_api_key="", llm_max_retries=0)
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _text_response(_VALID_JSON)

        llm.generate_itinerary_days(
            destination="Paris", days=1, budget=1000.0, trip_style="budget"
        )

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "tools" not in call_kwargs


def test_tool_use_loop_calls_weather_and_continues():
    weather_data = {"temperature_celsius": 22.0, "description": "sunny", "humidity_percent": 50}

    with patch("app.services.llm_itinerary.Anthropic") as mock_cls, \
         patch("app.services.llm_itinerary.get_current_weather") as mock_weather, \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(weather_api_key="weather-key", llm_max_retries=0)
        mock_weather.return_value = weather_data
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            _tool_use_response("tool_1", "get_current_weather", {"destination": "Paris"}),
            _text_response(_VALID_JSON),
        ]

        result = llm.generate_itinerary_days(
            destination="Paris", days=1, budget=1000.0, trip_style="budget"
        )

    assert len(result) == 1
    mock_weather.assert_called_once_with("Paris")
    assert mock_client.messages.create.call_count == 2


def test_rag_context_injected_into_system_prompt():
    kb_hits = [{"title": "Hidden gems", "content": "Visit Galerie Vivienne."}]

    with patch("app.services.llm_itinerary.Anthropic") as mock_cls, \
         patch("app.services.llm_itinerary.knowledge_base.search", return_value=kb_hits), \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(llm_max_retries=0)
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _text_response(_VALID_JSON)

        llm.generate_itinerary_days(
            destination="Paris", days=1, budget=1000.0, trip_style="budget"
        )

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "Local Knowledge" in call_kwargs["system"]
    assert "Galerie Vivienne" in call_kwargs["system"]


def test_rag_fallback_when_kb_empty():
    with patch("app.services.llm_itinerary.Anthropic") as mock_cls, \
         patch("app.services.llm_itinerary.knowledge_base.search", return_value=[]), \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(llm_max_retries=0)
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _text_response(_VALID_JSON)

        llm.generate_itinerary_days(
            destination="Paris", days=1, budget=1000.0, trip_style="budget"
        )

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "Local Knowledge" not in call_kwargs["system"]


def test_rag_fallback_when_kb_raises():
    with patch("app.services.llm_itinerary.Anthropic") as mock_cls, \
         patch("app.services.llm_itinerary.knowledge_base.search", side_effect=Exception("KB down")), \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(llm_max_retries=0)
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = _text_response(_VALID_JSON)

        result = llm.generate_itinerary_days(
            destination="Paris", days=1, budget=1000.0, trip_style="budget"
        )

    assert len(result) == 1
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "Local Knowledge" not in call_kwargs["system"]


def test_tool_use_weather_failure_does_not_abort_generation():
    with patch("app.services.llm_itinerary.Anthropic") as mock_cls, \
         patch("app.services.llm_itinerary.get_current_weather") as mock_weather, \
         patch("app.services.llm_itinerary.get_settings") as mock_settings:
        mock_settings.return_value = _mock_settings(weather_api_key="weather-key", llm_max_retries=0)
        mock_weather.side_effect = llm.WeatherServiceError("API down")
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            _tool_use_response("tool_1", "get_current_weather", {"destination": "Paris"}),
            _text_response(_VALID_JSON),
        ]

        result = llm.generate_itinerary_days(
            destination="Paris", days=1, budget=1000.0, trip_style="budget"
        )

    assert len(result) == 1
    assert mock_client.messages.create.call_count == 2
