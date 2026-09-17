from unittest.mock import MagicMock, patch

import pytest

from app.services.agent import run_travel_agent


def _mock_settings(**overrides):
    defaults = {
        "anthropic_api_key": "test-key",
        "anthropic_model": "claude-haiku-4-5-20251001",
        "anthropic_temperature": 0.7,
        "anthropic_max_tokens": 2000,
    }
    return MagicMock(**{**defaults, **overrides})


_VALID_JSON = '{"days": [{"day": 1, "activities": ["Eiffel Tower", "Louvre"]}]}'

_AGENT_INPUT = {
    "destination": "Paris",
    "days": 1,
    "budget": 1000.0,
    "trip_style": "cultural",
}


def _build_mock_llm(gather_content: str, format_content: str):
    gather_msg = MagicMock()
    gather_msg.content = gather_content

    format_msg = MagicMock()
    format_msg.content = format_content

    llm = MagicMock()
    llm.invoke.return_value = format_msg
    llm.bind_tools = MagicMock(return_value=llm)

    return llm, gather_msg


def test_run_travel_agent_returns_string():
    gather_msg = MagicMock()
    gather_msg.content = "Paris has great weather and many attractions."

    format_msg = MagicMock()
    format_msg.content = _VALID_JSON

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = format_msg
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    mock_agent_result = {"messages": [gather_msg]}

    with patch("app.services.agent.get_settings") as mock_settings, \
         patch("app.services.agent.ChatAnthropic", return_value=mock_llm), \
         patch("app.services.agent.create_react_agent") as mock_create:
        mock_settings.return_value = _mock_settings()
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = mock_agent_result
        mock_create.return_value = mock_graph

        result = run_travel_agent(_AGENT_INPUT)

    assert result == _VALID_JSON


def test_run_travel_agent_passes_all_tools():
    gather_msg = MagicMock()
    gather_msg.content = "Context gathered."

    format_msg = MagicMock()
    format_msg.content = _VALID_JSON

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = format_msg
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    with patch("app.services.agent.get_settings") as mock_settings, \
         patch("app.services.agent.ChatAnthropic", return_value=mock_llm), \
         patch("app.services.agent.create_react_agent") as mock_create:
        mock_settings.return_value = _mock_settings()
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"messages": [gather_msg]}
        mock_create.return_value = mock_graph

        run_travel_agent(_AGENT_INPUT)

    tools_passed = mock_create.call_args[0][1]
    tool_names = {t.name for t in tools_passed}
    assert "weather_tool" in tool_names
    assert "knowledge_tool" in tool_names
    assert "places_tool" in tool_names
    assert "pricing_tool" in tool_names


def test_run_travel_agent_includes_destination_in_gather_prompt():
    gather_msg = MagicMock()
    gather_msg.content = "Context."

    format_msg = MagicMock()
    format_msg.content = _VALID_JSON

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = format_msg
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    with patch("app.services.agent.get_settings") as mock_settings, \
         patch("app.services.agent.ChatAnthropic", return_value=mock_llm), \
         patch("app.services.agent.create_react_agent") as mock_create:
        mock_settings.return_value = _mock_settings()
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"messages": [gather_msg]}
        mock_create.return_value = mock_graph

        run_travel_agent(_AGENT_INPUT)

    invoke_args = mock_graph.invoke.call_args[0][0]
    messages_text = " ".join(m.content for m in invoke_args["messages"])
    assert "Paris" in messages_text


def test_run_travel_agent_passes_context_to_formatter():
    gather_msg = MagicMock()
    gather_msg.content = "Sunny, 22°C. Louvre nearby."

    format_msg = MagicMock()
    format_msg.content = _VALID_JSON

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = format_msg
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)

    with patch("app.services.agent.get_settings") as mock_settings, \
         patch("app.services.agent.ChatAnthropic", return_value=mock_llm), \
         patch("app.services.agent.create_react_agent") as mock_create:
        mock_settings.return_value = _mock_settings()
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"messages": [gather_msg]}
        mock_create.return_value = mock_graph

        run_travel_agent(_AGENT_INPUT)

    format_call_messages = mock_llm.invoke.call_args[0][0]
    combined = " ".join(m.content for m in format_call_messages)
    assert "Sunny, 22°C" in combined
    assert "Louvre nearby" in combined
