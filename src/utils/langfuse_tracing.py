"""Langfuse tracing setup.

OpenInference's DSPy instrumentor automatically captures every LLM call
(prompt, completion, token counts, latency, model parameters); this module adds
the half DSPy can't see: item mapping, address normalization, date validation,
duplicate checks, and writing to the spreadsheet.

How sessions are split: **one session per order**. The session_id is
"receiver | phone | delivery date", so every trace for the same order, from
parsing and the re-check through to writing the sheet, is tied together. If the
customer later amends the order and it is run again, it lands in the same
session, so the order's full history can be replayed.
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_initialized = False
_enabled = False


def is_enabled() -> bool:
    """Whether Langfuse is available. Without keys, tracing is silently disabled and the main flow is unaffected."""
    return _enabled


def setup() -> bool:
    """Initialize Langfuse and the DSPy instrumentor; return whether it was enabled.

    Safe to call repeatedly (Flask builds a new importer per request, but this
    only initializes once).
    """
    global _initialized, _enabled
    if _initialized:
        return _enabled

    _initialized = True

    if not (os.getenv('LANGFUSE_PUBLIC_KEY') and os.getenv('LANGFUSE_SECRET_KEY')):
        logger.info('LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY not set; Langfuse tracing disabled')
        return False

    try:
        from langfuse import get_client
        from openinference.instrumentation.dspy import DSPyInstrumentor

        client = get_client()
        if not client.auth_check():
            logger.warning('Langfuse auth failed; tracing disabled (check the keys and LANGFUSE_BASE_URL)')
            return False

        DSPyInstrumentor().instrument()
        _enabled = True
        logger.info(f'Langfuse tracing enabled: {os.getenv("LANGFUSE_BASE_URL")}')
    except Exception as error:
        # Broken tracing must never break order processing
        logger.warning(f'Langfuse initialization failed; tracing disabled: {error}')
        return False

    return _enabled


@contextmanager
def trace(name: str, session_id: Optional[str] = None,
          input_data: Any = None, metadata: Optional[Dict[str, Any]] = None):
    """Create a span, optionally attached to a session.

    When disabled it is a no-op context manager, so callers need no checks.
    The yielded object has .update(output=..., metadata=...) for adding results;
    when disabled it yields a _NullSpan, which also has .update(), so caller
    code is the same either way.
    """
    if not _enabled:
        yield _NullSpan()
        return

    try:
        from langfuse import get_client, propagate_attributes
    except ImportError:
        yield _NullSpan()
        return

    # Only the "create the span" part may fail silently; errors after the yield
    # are the caller's business errors and must propagate unchanged.
    #
    # This used to wrap the whole with-block (including the yield) in try/except:
    # as soon as the caller's body raised, it was caught here and yielded again.
    # contextmanager does not allow yielding after a throw, so Python turned it
    # into RuntimeError: generator didn't stop after throw(), and the real error
    # and traceback vanished, which made it very hard to debug.
    from contextlib import ExitStack

    stack = ExitStack()
    try:
        client = get_client()
        span = stack.enter_context(
            client.start_as_current_observation(as_type='span', name=name)
        )
        if input_data is not None:
            span.update(input=input_data)
        if metadata:
            span.update(metadata=metadata)
        if session_id:
            stack.enter_context(propagate_attributes(session_id=session_id[:200]))
    except Exception as error:
        logger.warning(f'Failed to create Langfuse span "{name}"; skipping tracing: {error}')
        stack.close()
        yield _NullSpan()
        return

    # ExitStack passes the body's exception to the span's cleanup correctly and keeps it propagating
    with stack:
        yield span


@contextmanager
def generation(name: str, *, model: Optional[str] = None, input_data: Any = None,
               metadata: Optional[Dict[str, Any]] = None,
               model_parameters: Optional[Dict[str, Any]] = None):
    """Create a generation observation for model calls the DSPy instrumentor can't see (e.g. Jev)

    Same contract as trace(): yields _NullSpan when disabled; only a failure to create the
    observation is swallowed, exceptions from the body propagate unchanged.
    Callers fill in the rest before exiting with
    span.update(output=..., model=..., usage_details=..., cost_details=...).
    """
    if not _enabled:
        yield _NullSpan()
        return

    from contextlib import ExitStack

    stack = ExitStack()
    try:
        from langfuse import get_client

        span = stack.enter_context(
            get_client().start_as_current_observation(
                as_type='generation', name=name, model=model, input=input_data,
                metadata=metadata, model_parameters=model_parameters,
            )
        )
    except Exception as error:
        logger.warning(f'Failed to create Langfuse generation "{name}", skipping tracing: {error}')
        stack.close()
        yield _NullSpan()
        return

    with stack:
        yield span


def score(name: str, value: float, comment: Optional[str] = None):
    """Score the current trace, to build up long-term parsing-quality statistics"""
    if not _enabled:
        return
    try:
        from langfuse import get_client
        get_client().score_current_trace(name=name, value=value, comment=comment)
    except Exception as error:
        logger.debug(f'Langfuse scoring failed: {error}')


def flush():
    """Send buffered tracing data.

    Programs that exit when done, like the CLI, must call this, otherwise the
    data is not sent before the process exits.
    """
    if not _enabled:
        return
    try:
        from langfuse import get_client
        get_client().flush()
    except Exception as error:
        logger.debug(f'Langfuse flush failed: {error}')


class _NullSpan:
    """Stand-in used when tracing is disabled, so callers don't need ifs everywhere"""

    def update(self, **kwargs):
        pass

    def score(self, **kwargs):
        pass


# --- Compatibility aliases ---
# dspy_client.py and openai_client.py use the init_tracing / observation /
# update_observation names, which are the same thing as this module's setup / trace.
# Both sets of names are kept so those two files' existing calls don't need changing.

init_tracing = setup


@contextmanager
def observation(name: str, input: Any = None, metadata: Optional[Dict[str, Any]] = None,
                session_id: Optional[str] = None):
    """Alias of trace(), with the parameter named input (instead of input_data)"""
    with trace(name, session_id=session_id, input_data=input, metadata=metadata) as span:
        yield span


def update_observation(span, **kwargs):
    """Add input/output/metadata to a span created by observation().

    span may be None or a _NullSpan (when tracing is disabled); both are safely skipped.
    """
    if span is None:
        return
    try:
        span.update(**kwargs)
    except Exception as error:
        logger.debug(f'Langfuse observation update failed: {error}')
