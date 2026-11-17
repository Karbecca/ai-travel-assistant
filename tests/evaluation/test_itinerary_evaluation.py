import json
import os

import pytest

from app.services.evaluation import GOLDEN_TEST_CASES, evaluate_itinerary_response


def _make_itinerary(destination: str, num_days: int, keywords: list[str]) -> list[dict]:
    days = []
    for i in range(1, num_days + 1):
        kw = keywords[i % len(keywords)]
        days.append({
            "day": i,
            "activities": [
                f"Morning activity in {destination} near {kw}",
                f"Afternoon exploring {destination}",
                f"Evening in {destination}",
            ],
        })
    return days


class TestRuntimeEvaluator:
    @pytest.mark.parametrize("case", GOLDEN_TEST_CASES)
    def test_completeness(self, case):
        itinerary = _make_itinerary(case["destination"], case["num_days"], case["must_contain_keywords"])
        report = evaluate_itinerary_response(itinerary, case["destination"], case["trip_style"], case["expected_days"])
        assert report.completeness_score == 1.0

    @pytest.mark.parametrize("case", GOLDEN_TEST_CASES)
    def test_format_valid(self, case):
        itinerary = _make_itinerary(case["destination"], case["num_days"], case["must_contain_keywords"])
        report = evaluate_itinerary_response(itinerary, case["destination"], case["trip_style"], case["expected_days"])
        assert report.format_valid is True

    @pytest.mark.parametrize("case", GOLDEN_TEST_CASES)
    def test_relevance_with_destination_in_activities(self, case):
        itinerary = _make_itinerary(case["destination"], case["num_days"], case["must_contain_keywords"])
        report = evaluate_itinerary_response(itinerary, case["destination"], case["trip_style"], case["expected_days"])
        assert report.relevance_score >= 0.5

    def test_wrong_day_count_fails_completeness(self):
        itinerary = _make_itinerary("Paris", 2, ["Eiffel"])
        report = evaluate_itinerary_response(itinerary, "Paris", "romantic", 3)
        assert report.completeness_score == 0.0
        assert report.overall_pass is False

    def test_missing_activities_field_fails_format(self):
        itinerary = [{"day": 1, "wrong_key": []}]
        report = evaluate_itinerary_response(itinerary, "Paris", "romantic", 1)
        assert report.format_valid is False


class TestDeepEvalSemantics:
    @pytest.fixture(autouse=True)
    def skip_without_key(self):
        try:
            import deepeval  # noqa: F401
        except ImportError:
            pytest.skip("deepeval not installed — skipping DeepEval semantic tests")
        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set — skipping DeepEval semantic tests")

    def test_destination_relevance(self):
        from deepeval import assert_test
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams

        from app.services.evaluation import AnthropicEvalLLM

        llm = AnthropicEvalLLM(api_key=os.getenv("ANTHROPIC_API_KEY"))
        itinerary = _make_itinerary("Tokyo", 3, ["temple", "museum"])

        metric = GEval(
            name="DestinationRelevance",
            criteria=(
                "The itinerary activities should be relevant to the requested destination."
            ),
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            model=llm,
            threshold=0.5,
        )
        test_case = LLMTestCase(
            input="3-day cultural itinerary for Tokyo",
            actual_output=json.dumps(itinerary),
        )
        assert_test(test_case, [metric])

    def test_day_count_completeness(self):
        from deepeval import assert_test
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams

        from app.services.evaluation import AnthropicEvalLLM

        llm = AnthropicEvalLLM(api_key=os.getenv("ANTHROPIC_API_KEY"))
        itinerary = _make_itinerary("Paris", 2, ["Eiffel"])

        metric = GEval(
            name="DayCountCompleteness",
            criteria="The itinerary must contain exactly the number of days requested.",
            evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
            model=llm,
            threshold=0.7,
        )
        test_case = LLMTestCase(
            input="2-day romantic itinerary for Paris",
            actual_output=json.dumps(itinerary),
        )
        assert_test(test_case, [metric])
