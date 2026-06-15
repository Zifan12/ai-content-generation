"""
Langfuse tracing decorator and helpers.

`traced` is the project's single tracing primitive — every LLM call and
non-trivial pipeline step wraps in it so cost, latency, and output show up in
one place. Without consistent use, observability gaps appear silently.
"""

from functools import wraps
from typing import Callable, Any
from langfuse import observe, get_client


def traced(
    name: str | None = None,
    capture_input: bool = True,
    capture_output: bool = True,
    kind: str = "span",  # "span" | "generation" (LLM-specific)
) -> Callable:
    """
    Decorator. Wrap function → span in Langfuse.
    
    - name: override span name (default: fn.__name__)
    - capture_input: record args/kwargs as span input
    - capture_output: record return value as span output
    - kind: "generation" for LLM calls (adds token/cost fields)
    
    Handles async + sync. Nested calls auto-parent via contextvar.
    """
    def decorator(fn):
        return observe(name=name, capture_input=capture_input, capture_output=capture_output, as_type=kind)(fn)
    return decorator

def get_current_span():
    """
    Return active span from contextvar, or None.
    """
    return get_client().get_current_observation()

def flush():
    """
    Force send queued events. Call on shutdown.
    """
    get_client().flush()
