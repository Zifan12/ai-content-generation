"""LangGraph tool: fetch one specific URL's full page content via Firecrawl.

Used when tavily_search has already found a page but its snippet-only
result doesn't carry a structured fact (e.g. a Fandom wiki infobox field)
— see docs/superpowers/specs/2026-07-08-context-agent-grounding-hardening-design.md.

Targets Fandom's standardized "Portable Infobox" widget specifically
(``include_tags=["aside.portable-infobox"]``) rather than disabling content
filtering entirely. Confirmed live (2026-07-08) against a real Fandom URL:
this returns only the infobox's fields, no ad/nav/unrelated-widget content
— the same page scraped with filtering fully off (``only_main_content=False``)
was confirmed to also pull in an ad placeholder and an unrelated "Recent
Images" widget through a second, non-infobox ``<aside>`` element on the
same page. "portable-infobox" is a Fandom platform-wide class name, not
specific to this one wiki.
"""

import os

from src.monitor.tools._types import ToolResult


def firecrawl_extract(
    url: str,
    *,
    api_key: str | None = None,
    client=None,
) -> ToolResult:
    """Fetch ``url``'s Fandom-infobox content in full.

    Args:
        url: The page to fetch. Callers are responsible for confirming this
            URL was actually returned by a prior real search (see
            ``_act_firecrawl_extract``'s validation) — this function just
            fetches whatever URL it's given, with no such check itself.
        api_key: Firecrawl API key. Defaults to the ``FIRECRAWL_API_KEY``
            env var.
        client: Optional seam for tests — an already-constructed client (or
            compatible fake exposing ``.scrape(url, **kwargs)`` returning an
            object with a ``.markdown`` attribute). Defaults to a real
            ``FirecrawlApp``, so tests can exercise the formatting with no
            network.

    Returns:
        A ``ToolResult``. Its ``text`` is the fetched page's markdown
        content (empty string if the fetch returned nothing). Its ``urls``
        is always empty — this reads a URL a search already found, it does
        not discover new ones.

    Raises:
        RuntimeError: if no Firecrawl API key is configured and no
            ``client`` was injected.
    """
    if client is None:
        key = api_key or os.environ.get("FIRECRAWL_API_KEY")
        if not key:
            raise RuntimeError(
                "FIRECRAWL_API_KEY is not set — needed by firecrawl_extract. "
                "Put it in config/.env."
            )
        from firecrawl import FirecrawlApp

        client = FirecrawlApp(api_key=key)

    doc = client.scrape(
        url,
        only_main_content=True,
        include_tags=["aside.portable-infobox"],
    )
    text = getattr(doc, "markdown", None) or ""
    return ToolResult(text=text, urls=[])
