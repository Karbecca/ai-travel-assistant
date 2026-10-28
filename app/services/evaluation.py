from dataclasses import dataclass, field

try:
    import anthropic
    from deepeval.models.base_model import DeepEvalBaseLLM

    class AnthropicEvalLLM(DeepEvalBaseLLM):
        def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
            self._client = anthropic.Anthropic(api_key=api_key)
            self._model = model

        def load_model(self):
            return self._model

        def generate(self, prompt: str) -> str:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text

        async def a_generate(self, prompt: str) -> str:
            return self.generate(prompt)

        def get_model_name(self) -> str:
            return self._model

except ImportError:
    AnthropicEvalLLM = None  # type: ignore


@dataclass
class EvaluationReport:
    relevance_score: float
    completeness_score: float
    format_valid: bool
    overall_pass: bool
    details: dict = field(default_factory=dict)


GOLDEN_TEST_CASES = [
    {
        "destination": "Tokyo",
        "trip_style": "cultural",
        "num_days": 3,
        "expected_days": 3,
        "must_contain_keywords": ["Tokyo", "temple", "museum"],
    },
    {
        "destination": "Paris",
        "trip_style": "romantic",
        "num_days": 2,
        "expected_days": 2,
        "must_contain_keywords": ["Paris", "Eiffel"],
    },
    {
        "destination": "Bali",
        "trip_style": "relaxation",
        "num_days": 5,
        "expected_days": 5,
        "must_contain_keywords": ["Bali", "beach", "temple"],
    },
    {
        "destination": "New York",
        "trip_style": "adventure",
        "num_days": 4,
        "expected_days": 4,
        "must_contain_keywords": ["New York", "Manhattan"],
    },
]


def evaluate_itinerary_response(
    itinerary: list,
    destination: str,
    trip_style: str,
    expected_days: int,
) -> EvaluationReport:
    completeness = 1.0 if len(itinerary) == expected_days else 0.0

    format_valid = all(
        isinstance(d.get("day"), int) and isinstance(d.get("activities"), list)
        for d in itinerary
    )

    all_text = " ".join(
        " ".join(d.get("activities", [])) for d in itinerary
    ).lower()
    dest_hit = destination.lower() in all_text
    style_hit = trip_style.lower() in all_text
    relevance = (0.5 if dest_hit else 0.0) + (0.5 if style_hit else 0.0)

    overall = relevance >= 0.5 and completeness == 1.0 and format_valid

    return EvaluationReport(
        relevance_score=relevance,
        completeness_score=completeness,
        format_valid=format_valid,
        overall_pass=overall,
        details={
            "destination_mentioned": str(dest_hit),
            "style_mentioned": str(style_hit),
            "day_count": f"{len(itinerary)}/{expected_days}",
        },
    )
