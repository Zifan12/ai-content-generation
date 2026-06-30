"""Shared return type for tool functions in this package."""

from typing import NamedTuple


class ToolResult(NamedTuple):
    """A tool function's formatted text plus the URLs it found, kept separate
    so callers can use the text for an LLM prompt and the URLs as a
    structured reference list (e.g. ContextBundle.references) without having
    to re-parse them back out of the text.
    """

    text: str
    urls: list[str]
