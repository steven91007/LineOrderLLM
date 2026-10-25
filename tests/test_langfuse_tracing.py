"""Offline checks of src/utils/langfuse_tracing.py behavior on the Langfuse Python SDK v4

Does not connect to any Langfuse server: OpenTelemetry's InMemorySpanExporter captures the spans the SDK produces,
and the tests check that everything the v4 observations-first data model needs is in place:
- the root observation carries input/output
- propagate_attributes puts session_id on the root and on every child observation
- when disabled, every API is a no-op and caller exceptions still propagate
"""
import importlib
import os

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

SESSION_ATTR = "session.id"  # SDK v4 writes the session as an OTel attribute on every observation


@pytest.fixture
def tracing(monkeypatch):
    """Give every test a clean module state and route the SDK's spans to memory"""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "http://localhost:9")  # never actually connected to

    from langfuse import Langfuse
    from langfuse._client.resource_manager import LangfuseResourceManager

    # The SDK caches the client (and its exporter) keyed by public key; clear it so each test gets its own exporter
    with LangfuseResourceManager._lock:
        LangfuseResourceManager._instances.clear()

    exporter = InMemorySpanExporter()
    monkeypatch.setattr(Langfuse, "auth_check", lambda self: True)
    Langfuse(span_exporter=exporter, flush_at=1, flush_interval=0.05)

    import src.utils.langfuse_tracing as module

    module = importlib.reload(module)
    module.exporter = exporter  # exposed for the tests
    yield module
    module.flush()


def _spans(tracing):
    tracing.flush()
    return {s.name: s for s in tracing.exporter.get_finished_spans()}


def test_setup_enables_tracing_and_dspy_instrumentor(tracing):
    assert tracing.setup() is True
    assert tracing.is_enabled()
    assert tracing.setup() is True  # calling again is safe


def test_root_observation_carries_input_output_and_session(tracing):
    tracing.setup()
    with tracing.trace("order-build", session_id="王小明｜0912｜2026-10-01",
                       input_data={"raw": "x"}, metadata={"source": "test"}) as span:
        with tracing.trace("normalize-address", input_data={"raw": "台北"}) as child:
            child.update(output="臺北市")
        span.update(output={"row": [1, 2]})

    spans = _spans(tracing)
    root, child = spans["order-build"], spans["normalize-address"]
    assert child.parent.span_id == root.context.span_id
    assert root.attributes["langfuse.observation.type"] == "span"
    assert "raw" in root.attributes["langfuse.observation.input"]
    assert "row" in root.attributes["langfuse.observation.output"]
    # v4: the session must be on every observation, both the root and the child spans
    assert root.attributes[SESSION_ATTR] == "王小明｜0912｜2026-10-01"
    assert child.attributes[SESSION_ATTR] == "王小明｜0912｜2026-10-01"


def test_separate_traces_keep_their_own_session(tracing):
    tracing.setup()
    for key in ("A", "B"):
        with tracing.trace("order-build", session_id=key, input_data=key):
            pass
    tracing.flush()
    finished = tracing.exporter.get_finished_spans()
    sessions = sorted(s.attributes[SESSION_ATTR] for s in finished if s.name == "order-build")
    trace_ids = {s.context.trace_id for s in finished if s.name == "order-build"}
    assert sessions == ["A", "B"]
    assert len(trace_ids) == 2


def test_session_id_is_capped_to_200_chars(tracing):
    tracing.setup()
    with tracing.trace("order-build", session_id="x" * 300):
        pass
    assert _spans(tracing)["order-build"].attributes[SESSION_ATTR] == "x" * 200


def test_body_exceptions_propagate_and_span_still_exported(tracing):
    tracing.setup()
    with pytest.raises(ValueError, match="boom"):
        with tracing.trace("write-to-sheet", session_id="S"):
            raise ValueError("boom")
    span = _spans(tracing)["write-to-sheet"]
    assert span.status.status_code.name == "ERROR"


def test_disabled_without_keys_is_noop(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    import src.utils.langfuse_tracing as module

    module = importlib.reload(module)
    assert module.setup() is False
    with module.trace("order-build", session_id="S", input_data=1) as span:
        span.update(output=2)  # _NullSpan
    module.score("ready_ratio", 1.0)
    module.flush()
    with pytest.raises(RuntimeError):
        with module.trace("x"):
            raise RuntimeError("still raised when disabled")
