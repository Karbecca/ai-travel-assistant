from langchain_core.tools import tool

_COST_TIERS: dict[str, tuple[float, float]] = {
    "western europe": (120.0, 200.0),
    "eastern europe": (50.0, 90.0),
    "north america": (110.0, 180.0),
    "southeast asia": (30.0, 60.0),
    "east asia": (70.0, 130.0),
    "south asia": (25.0, 55.0),
    "middle east": (80.0, 150.0),
    "africa": (40.0, 80.0),
    "latin america": (45.0, 85.0),
    "oceania": (120.0, 200.0),
}

_CITY_REGION: dict[str, str] = {
    "paris": "western europe", "london": "western europe", "rome": "western europe",
    "barcelona": "western europe", "amsterdam": "western europe", "berlin": "western europe",
    "prague": "eastern europe", "budapest": "eastern europe", "warsaw": "eastern europe",
    "new york": "north america", "los angeles": "north america", "toronto": "north america",
    "bangkok": "southeast asia", "bali": "southeast asia", "singapore": "southeast asia",
    "tokyo": "east asia", "seoul": "east asia", "beijing": "east asia",
    "mumbai": "south asia", "delhi": "south asia", "colombo": "south asia",
    "dubai": "middle east", "istanbul": "middle east", "cairo": "africa",
    "nairobi": "africa", "cape town": "africa", "marrakech": "africa",
    "mexico city": "latin america", "rio de janeiro": "latin america", "buenos aires": "latin america",
    "sydney": "oceania", "melbourne": "oceania", "auckland": "oceania",
}


@tool
def pricing_tool(destination: str, days: int, budget: float) -> str:
    """Estimate whether a travel budget is sufficient and suggest a daily spending plan."""
    region = _CITY_REGION.get(destination.lower())
    if region is None:
        for key in _CITY_REGION:
            if key in destination.lower() or destination.lower() in key:
                region = _CITY_REGION[key]
                break

    if region is None:
        region = "western europe"

    low, high = _COST_TIERS[region]
    daily = budget / days if days > 0 else 0
    midpoint = (low + high) / 2

    if daily >= high:
        tier = "comfortable"
    elif daily >= midpoint:
        tier = "moderate"
    elif daily >= low:
        tier = "budget-friendly"
    else:
        tier = "tight"

    return (
        f"Budget assessment for {destination} ({days} days, ${budget:.0f} total): "
        f"${daily:.0f}/day — {tier}. "
        f"Typical range for this region is ${low:.0f}–${high:.0f}/day."
    )
