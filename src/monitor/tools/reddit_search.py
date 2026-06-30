"""LangGraph tool: search Reddit for posts/comments matching a free-text query.

Reuses the same Apify ``harshmaur/reddit-scraper`` actor and ``APIFY_API_TOKEN``
the Reddit cultural monitor already uses (see ``src/monitor/scraper.py``), but
in the actor's search mode (``searchTerms``) instead of subreddit-listing mode
(``startUrls``). The actor's input schema exposes search natively, so this is
the same provider/token/item-shape, just a different run-input — no new cost
surface beyond the existing Apify billing.
"""

import os
from typing import Callable

import httpx

from src.monitor.tools._types import ToolResult

_APIFY_BASE_URL = "https://api.apify.com/v2"
_DEFAULT_REDDIT_ACTOR = "harshmaur/reddit-scraper"


def reddit_search(
    query: str,
    *,
    api_token: str | None = None,
    actor_id: str = _DEFAULT_REDDIT_ACTOR,
    max_items: int = 20,
    max_comments_per_post: int = 20,
    timeout_seconds: float = 120.0,
    item_fetcher: Callable[[dict], list[dict]] | None = None,
) -> ToolResult:
    """Search Reddit for ``query`` and return matching posts/comments as one text blob.

    Args:
        query: Free-text search term (e.g. a topic name or character name).
        api_token: Apify API token. Defaults to the ``APIFY_API_TOKEN`` env var.
        actor_id: Apify actor id (slash form); tilde-encoded for the URL path.
        max_items: Cap on items returned by the actor (``maxItems``).
        max_comments_per_post: Comments to crawl per matched post
            (``maxCommentsPerPost``). ``searchComments`` alone only matches
            comment *text* as a search target — it does NOT include comment
            items in the output. ``crawlCommentsPerPost`` is what actually
            triggers comment scraping (confirmed via a live probe run:
            ``searchComments=True`` alone returned posts only, despite
            matched posts having hundreds of real comments).
        timeout_seconds: HTTP timeout for the synchronous actor run.
        item_fetcher: Optional seam for tests — a callable taking the run-input
            dict and returning the raw list of actor items. Defaults to the
            real Apify call, so tests can exercise the formatting with no
            network.

    Returns:
        A ``ToolResult``. Its ``text`` is one block per matched post: a
        ``[POST]`` title line followed by its own comments as indented
        ``[COMMENT]`` lines, blocks separated by a blank line. Comments are
        grouped under their post via ``postId`` — the actor's raw item order
        interleaves posts and comments from different threads, so grouping
        (not print order) is what keeps a comment attributed to the right
        post. Empty string if nothing matched. Posts with no matched
        comments still get their own block. Its ``urls`` is each matched
        post's ``postUrl``, in the same order as the text blocks.

    Raises:
        RuntimeError: if no Apify token is configured and no ``item_fetcher``
            was injected.
    """
    token = api_token or os.environ.get("APIFY_API_TOKEN")
    if item_fetcher is None and not token:
        raise RuntimeError(
            "APIFY_API_TOKEN is not set — needed by reddit_search. "
            "Put it in config/.env."
        )

    run_input = {
        "searchTerms": [query],
        "searchPosts": True,
        "searchComments": True,
        "maxItems": max_items,
        "crawlCommentsPerPost": True,
        "maxCommentsPerPost": max_comments_per_post,
        "searchSort": "relevance",
        "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
    }

    fetcher = item_fetcher or _make_apify_fetcher(actor_id, token, timeout_seconds)
    items = fetcher(run_input)

    # Bucket comments by their post first (same pattern as
    # ApifyRedditScraper._items_to_events) — the actor's raw item order does
    # NOT keep a post's comments adjacent to it, so grouping has to happen
    # explicitly via postId, not by trusting list order.
    comments_by_post: dict[str, list[dict]] = {}
    for item in items:
        if item.get("dataType") != "comment":
            continue
        post_id = item.get("postId")
        if post_id is None:
            continue
        bare_post_id = str(post_id).removeprefix("t3_")
        comments_by_post.setdefault(bare_post_id, []).append(item)

    blocks: list[str] = []
    urls: list[str] = []
    for item in items:
        if item.get("dataType") != "post":
            continue
        bare_id = str(item.get("id") or "").removeprefix("t3_")
        post_lines = [f"[POST] {item.get('title') or ''}"]
        for comment in comments_by_post.get(bare_id, []):
            post_lines.append(f"  [COMMENT] {comment.get('body') or ''}")
        blocks.append("\n".join(post_lines))
        post_url = item.get("postUrl")
        if post_url:
            urls.append(post_url)

    return ToolResult(text="\n\n".join(blocks).strip(), urls=urls)


def _make_apify_fetcher(
    actor_id: str, api_token: str | None, timeout_seconds: float
) -> Callable[[dict], list[dict]]:
    """Build the default ``item_fetcher``: a real synchronous Apify actor call.

    Uses Apify's ``run-sync-get-dataset-items`` endpoint, which starts the
    run, waits for it to finish, and returns the dataset items in one call —
    same pattern as ``ApifyRedditScraper._fetch_from_apify``.
    """

    def _fetch(run_input: dict) -> list[dict]:
        actor_path = actor_id.replace("/", "~")
        url = f"{_APIFY_BASE_URL}/acts/{actor_path}/run-sync-get-dataset-items"
        response = httpx.post(
            url,
            params={"token": api_token},
            json=run_input,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    return _fetch
