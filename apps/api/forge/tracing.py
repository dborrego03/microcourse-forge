"""OpenTelemetry tracing for the lesson pipeline.

Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set. Locally that points at Jaeger
(`docker compose --profile tracing up -d`, UI on :16686); in the cloud it can point
at Langfuse's OTLP endpoint with OTEL_EXPORTER_OTLP_HEADERS carrying the auth
header. Either way the code only speaks plain OTLP.
"""

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from opentelemetry import trace
from opentelemetry.trace import Span

from forge.llm import LLMResult
from forge.version import git_sha

if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": "microcourse-forge-api", "service.version": git_sha()})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

tracer = trace.get_tracer("forge")


@dataclass
class Step:
    name: str
    span: Span
    started: float = field(default_factory=time.perf_counter)
    ended: float | None = None
    result: LLMResult | None = None
    retries: int = 0

    def record(self, result: LLMResult | None, retries: int = 0) -> None:
        """Keep the model call's numbers for the runs table and put them on the span."""
        self.result, self.retries = result, retries
        if result:
            self.span.set_attributes(
                {
                    "gen_ai.system": "anthropic",
                    "gen_ai.request.model": result.model,
                    "gen_ai.usage.input_tokens": result.tokens_in,
                    "gen_ai.usage.output_tokens": result.tokens_out,
                    "forge.cost_usd": result.cost_usd,
                    "forge.cached": result.cached,
                    "forge.retries": retries,
                }
            )

    @property
    def ms(self) -> int:
        return round(((self.ended or time.perf_counter()) - self.started) * 1000)

    @property
    def trace_id(self) -> str | None:
        context = self.span.get_span_context()
        return format(context.trace_id, "032x") if context.is_valid else None


@contextmanager
def step(name: str) -> Iterator[Step]:
    """Times a pipeline step and wraps it in a span. The timing works with tracing off too."""
    with tracer.start_as_current_span(name) as span:
        current = Step(name, span)
        try:
            yield current
        finally:
            current.ended = time.perf_counter()
