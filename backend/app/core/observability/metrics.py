"""
Prometheus metrics.

DESIGN: the HTTP metrics here are table stakes — every service has them.
The metrics that earn their keep in THIS system are the domain-specific
ones, because the questions that actually matter are:

  "Which agent is burning the most time and money?"
  "Is our LLM provider degrading?"
  "How often does the pipeline halt, and at which step?"

Generic request counts answer none of those. An LLM-heavy application's
cost and latency live almost entirely in agent execution, so that's what's
instrumented in detail.

Buckets are chosen for LLM latencies (seconds to tens of seconds), not the
web-request defaults (milliseconds), which would put every agent call in
the overflow bucket and make the histograms useless.
"""
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

# A dedicated registry rather than the global default: the default is
# process-wide mutable state, which makes tests order-dependent and
# re-registration errors common.
REGISTRY = CollectorRegistry()

# --- HTTP (table stakes) ---

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)

# --- Agents (the useful part) ---

agent_runs_total = Counter(
    "agent_runs_total",
    "Agent executions by outcome",
    ["agent", "outcome"],  # outcome: success | failure
    registry=REGISTRY,
)

agent_duration_seconds = Histogram(
    "agent_duration_seconds",
    "Agent execution duration",
    ["agent"],
    # Tuned for LLM latency. Web-default buckets would put nearly every
    # observation in +Inf and tell you nothing.
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0),
    registry=REGISTRY,
)

# --- LLM calls ---

llm_calls_total = Counter(
    "llm_calls_total",
    "LLM API calls by outcome",
    ["provider", "outcome"],  # outcome: success | malformed | error
    registry=REGISTRY,
)

llm_duration_seconds = Histogram(
    "llm_duration_seconds",
    "LLM API call duration",
    ["provider"],
    buckets=(0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0, 60.0),
    registry=REGISTRY,
)

llm_retries_total = Counter(
    "llm_retries_total",
    "LLM call retries — a rising rate signals provider or prompt degradation",
    ["reason"],  # reason: malformed_json | validation_error
    registry=REGISTRY,
)

# --- Pipeline ---

pipeline_runs_total = Counter(
    "pipeline_runs_total",
    "Pipeline executions by outcome",
    ["outcome"],  # outcome: completed | halted
    registry=REGISTRY,
)

pipeline_duration_seconds = Histogram(
    "pipeline_duration_seconds",
    "Full pipeline duration for one resume",
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
    registry=REGISTRY,
)

pipeline_halts_total = Counter(
    "pipeline_halts_total",
    "Pipeline halts by the step that failed",
    ["step"],
    registry=REGISTRY,
)

# --- Vector search ---

vector_search_total = Counter(
    "vector_search_total",
    "Vector searches performed",
    ["outcome"],
    registry=REGISTRY,
)

indexed_documents = Gauge(
    "indexed_documents",
    "Documents currently indexed for semantic search",
    ["collection"],
    registry=REGISTRY,
)


def render_metrics() -> bytes:
    """Render the registry in Prometheus text exposition format."""
    return generate_latest(REGISTRY)


def record_agent_run(agent: str, success: bool, duration_seconds: float) -> None:
    agent_runs_total.labels(agent=agent, outcome="success" if success else "failure").inc()
    agent_duration_seconds.labels(agent=agent).observe(duration_seconds)


def record_llm_call(provider: str, outcome: str, duration_seconds: float) -> None:
    llm_calls_total.labels(provider=provider, outcome=outcome).inc()
    llm_duration_seconds.labels(provider=provider).observe(duration_seconds)


def record_llm_retry(reason: str) -> None:
    llm_retries_total.labels(reason=reason).inc()


def record_pipeline_run(halted: bool, duration_seconds: float, halt_step: str | None = None) -> None:
    pipeline_runs_total.labels(outcome="halted" if halted else "completed").inc()
    pipeline_duration_seconds.observe(duration_seconds)
    if halted and halt_step:
        pipeline_halts_total.labels(step=halt_step).inc()
