import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

try:
    from datadog import initialize, statsd as _raw_statsd
    _DATADOG_AVAILABLE = True
except ImportError:
    _DATADOG_AVAILABLE = False
    _raw_statsd = None

_statsd = None
_dd_env = "development"
_dd_service = "ai-travel-assistant"


class _NoopSpan:
    def set_tag(self, *a, **kw): pass
    def set_error(self, *a, **kw): pass


@contextmanager
def _noop_trace(_name, **_kw):
    yield _NoopSpan()


def setup_datadog(settings) -> None:
    global _statsd, _dd_env, _dd_service
    _dd_env = settings.dd_env
    _dd_service = settings.dd_service
    if not _DATADOG_AVAILABLE:
        logger.warning("datadog package not installed — observability disabled")
        return
    try:
        initialize(statsd_host=settings.dd_agent_host, statsd_port=settings.dd_statsd_port)
        _statsd = _raw_statsd
        logger.info("Datadog observability initialised (%s:%s)", settings.dd_agent_host, settings.dd_statsd_port)
    except Exception as exc:
        logger.warning("Datadog init failed: %s — observability disabled", exc)


def record_llm_call(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    success: bool,
) -> None:
    if _statsd is None:
        return
    tags = [f"model:{model}", f"success:{str(success).lower()}", f"env:{_dd_env}"]
    _statsd.gauge("travel_assistant.llm.latency_ms", latency_ms, tags=tags)
    _statsd.gauge("travel_assistant.llm.prompt_tokens", prompt_tokens, tags=tags)
    _statsd.gauge("travel_assistant.llm.completion_tokens", completion_tokens, tags=tags)
    _statsd.increment("travel_assistant.llm.calls", tags=tags)


def record_guardrail_rejection(rejection_type: str, field: str = "") -> None:
    if _statsd is None:
        return
    tags = [f"type:{rejection_type}", f"field:{field}", f"env:{_dd_env}"]
    _statsd.increment("travel_assistant.guardrail.rejection", tags=tags)


def record_evaluation_score(relevance: float, completeness: float, passed: bool) -> None:
    if _statsd is None:
        return
    tags = [f"env:{_dd_env}"]
    _statsd.gauge("travel_assistant.evaluation.relevance", relevance, tags=tags)
    _statsd.gauge("travel_assistant.evaluation.completeness", completeness, tags=tags)
    _statsd.gauge("travel_assistant.evaluation.pass_rate", 1.0 if passed else 0.0, tags=tags)


def get_tracer():
    try:
        if _DATADOG_AVAILABLE:
            from ddtrace import tracer
            return tracer
    except Exception:
        pass
    return type("_Noop", (), {"trace": staticmethod(_noop_trace)})()
