"""
OpenTelemetry tracing.

SCOPE: instrumentation is wired now; the exporter defaults to console
because no OTLP collector exists in this deployment yet (that's Phase
21/22 infrastructure). Setting OTEL_EXPORTER_OTLP_ENDPOINT switches to a
real collector with no code change.

Instrumenting now with a console exporter is deliberate: adding spans later
means touching every agent again, whereas the exporter is one config value.

Tracing is OFF by default. Console-exported spans are extremely verbose and
would drown the structured logs during normal development.
"""
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

_configured = False


def configure_tracing(
    service_name: str = "resume-screening-platform",
    enabled: bool = False,
    otlp_endpoint: str = "",
) -> None:
    """Install the tracer provider. Idempotent."""
    global _configured
    if _configured or not enabled:
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            )
        except ImportError:
            # The OTLP exporter is an optional extra. Falling back to
            # console beats failing to start over a telemetry dependency.
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _configured = True


def get_tracer(name: str):
    return trace.get_tracer(name)


@contextmanager
def span(name: str, **attributes):
    """Start a span with attributes.

    A no-op when tracing is disabled: OpenTelemetry's default provider
    returns non-recording spans, so instrumented code costs almost nothing
    when tracing is off.
    """
    tracer = trace.get_tracer("app")
    with tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, str(value))
        yield current
