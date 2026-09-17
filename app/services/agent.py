from typing import TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from app.core.config import get_settings
from app.services.tools.knowledge_tool import knowledge_tool
from app.services.tools.places_tool import places_tool
from app.services.tools.pricing_tool import pricing_tool
from app.services.tools.weather_tool import weather_tool

_GATHER_PROMPT = """You are a travel research assistant.
Your job is to collect useful context for planning a trip using the available tools.
Call the tools that are relevant to the destination and request — you do not need to call all of them.
After gathering information, summarise the findings in a few sentences.
Do not produce an itinerary yet."""

_FORMAT_PROMPT = """You are a travel itinerary planner.
Return ONLY valid JSON with this exact shape:
{{"days": [{{"day": 1, "activities": ["activity 1", "activity 2"]}}, ...]}}
Rules:
- Match the exact number of days specified
- Number days from 1 through N with no gaps or duplicates
- Every activity must be located in or very near the destination
- Respect the stated budget and travel style
- Suggest 3 to 6 realistic activities per day
- Incorporate any weather, places, and knowledge context provided
- Do not include prices, booking links, or any text outside the JSON"""


class AgentInput(TypedDict):
    destination: str
    days: int
    budget: float
    trip_style: str


def run_travel_agent(input: AgentInput) -> str:
    """Run the two-step LangGraph agent and return raw JSON string."""
    settings = get_settings()
    llm = ChatAnthropic(
        model=settings.anthropic_model,
        api_key=settings.anthropic_api_key,
        temperature=settings.anthropic_temperature,
        max_tokens=settings.anthropic_max_tokens,
    )

    tools = [weather_tool, knowledge_tool, places_tool, pricing_tool]
    gather_agent = create_react_agent(llm, tools)

    gather_prompt = (
        f"Destination: {input['destination']}\n"
        f"Duration: {input['days']} days\n"
        f"Budget: ${input['budget']:.0f}\n"
        f"Style: {input['trip_style']}\n"
        "Gather relevant travel context using the available tools."
    )

    result = gather_agent.invoke({
        "messages": [
            SystemMessage(content=_GATHER_PROMPT),
            HumanMessage(content=gather_prompt),
        ]
    })

    context_summary = result["messages"][-1].content

    format_prompt = (
        f"Using the following research, plan a {input['days']}-day trip to "
        f"{input['destination']} with a budget of ${input['budget']:.0f} "
        f"and travel style '{input['trip_style']}'.\n\n"
        f"Research summary:\n{context_summary}"
    )

    format_response = llm.invoke([
        SystemMessage(content=_FORMAT_PROMPT),
        HumanMessage(content=format_prompt),
    ])

    return format_response.content
