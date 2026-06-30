"""LangGraph tool: general web search via the Tavily API.

Wraps ``tavily-python``'s ``TavilyClient.search()``. Tavily was picked over
Perplexity/Firecrawl for this role because it returns raw result snippets
rather than a synthesized answer — the agent does its own reasoning over the
results instead of outsourcing it to another LLM (see the context-agent
design spec). Free tier covers v1 volume.
"""

import os

from tavily import TavilyClient

from src.monitor.tools._types import ToolResult


def tavily_search(
    query: str,
    *,
    api_key: str | None = None,
    max_results: int = 5,
    client: TavilyClient | None = None,
) -> ToolResult:
    """Search the web for ``query`` and return title/url/snippet per result.

    Args:
        query: Free-text search term.
        api_key: Tavily API key. Defaults to the ``TAVILY_API_KEY`` env var.
        max_results: Maximum number of results to request from Tavily.
        client: Optional seam for tests — an already-constructed
            ``TavilyClient`` (or compatible fake exposing ``.search()``).
            Defaults to a real client built from ``api_key``, so tests can
            exercise the formatting with no network.

    Returns:
        A ``ToolResult``. Its ``text`` is one block per result — ``"{title}
        — {url}\\n{content}"`` — separated by blank lines, in the order
        Tavily ranked them. Empty string if nothing matched. Its ``urls`` is
        each result's ``url``, same order, kept separate from the text so
        callers don't have to re-parse them back out.

    Raises:
        RuntimeError: if no Tavily API key is configured and no ``client``
            was injected.
    """
    if client is None:
        key = api_key or os.environ.get("TAVILY_API_KEY")
        if not key:
            raise RuntimeError(
                "TAVILY_API_KEY is not set — needed by tavily_search. "
                "Put it in config/.env."
            )
        client = TavilyClient(api_key=key)

    response = client.search(query, max_results=max_results)
    results = response.get("results", [])

    blocks: list[str] = []
    urls: list[str] = []
    for result in results:
        title = result.get("title") or ""
        url = result.get("url") or ""
        content = result.get("content") or ""
        blocks.append(f"{title} — {url}\n{content}")
        if url:
            urls.append(url)
    return ToolResult(text="\n\n".join(blocks).strip(), urls=urls)
