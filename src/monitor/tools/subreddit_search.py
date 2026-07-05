"""LangGraph tool: find the Reddit communities matching a query, with sizes.

Uses the same Apify actor and ``APIFY_API_TOKEN`` as ``reddit_search``
(``harshmaur/reddit-scraper``), but in the actor's *community* search mode
(``searchCommunities``) rather than post search. Returns each matched
community's name, title, subscriber count and nsfw flag, so the caller can
pick the largest dedicated subreddit for a topic instead of guessing.

See docs/superpowers/specs/2026-07-04-community-lookup-by-size-design.md.
"""

import os
from typing import Callable, NamedTuple

import httpx

_APIFY_BASE_URL = "https://api.apify.com/v2"
_DEFAULT_REDDIT_ACTOR = "harshmaur/reddit-scraper"

# Community search bills a per-run BASE charge that dominates at this item
# count, so it is priced as a flat per-run cost, NOT reddit_search's per-item
# post rate. Measured 2026-07-04 (billed usageTotalUsd): 5 communities = $0.029,
# 8 = $0.0344 -> ~$0.020 base + ~$0.0018/community -> flat ~$0.035 at
# max_communities=8. Reusing the $0.002/item post rate (8*0.002=$0.016) misses
# the base charge and under-estimates ~2x (BUG-003 class).
COMMUNITY_SEARCH_COST = 0.035


class Subreddit(NamedTuple):
    """One community returned by ``search_subreddits``.

    name: bare subreddit name, no ``r/`` prefix (e.g. ``"ShingekiNoKyojin"``).
    title: display title. Often spells the IP out in English even when the
        name is foreign (``"Shingeki No Kyojin (Attack on Titan)"``), which is
        why the caller's token match checks title, not just name.
    members: subscriber count; 0 when the actor returned no usable count.
    nsfw: the community's over-18 flag.
    """

    name: str
    title: str
    members: int
    nsfw: bool


def search_subreddits(
    query: str,
    *,
    api_token: str | None = None,
    actor_id: str = _DEFAULT_REDDIT_ACTOR,
    max_communities: int = 8,
    timeout_seconds: float = 120.0,
    item_fetcher: Callable[[dict], list[dict]] | None = None,
) -> list[Subreddit]:
    """Search Reddit for communities matching ``query``.

    Args:
        query: Free-text search phrase — typically the topic or IP name.
        api_token: Apify token. Defaults to the ``APIFY_API_TOKEN`` env var.
        actor_id: Apify actor id (slash form); tilde-encoded for the URL path.
        max_communities: Cap on returned communities (``maxCommunitiesCount``).
            Results come back in relevance order, not size order, so this is a
            candidate pool the caller size-ranks — not a top-1.
        timeout_seconds: HTTP timeout for the synchronous actor run.
        item_fetcher: Test seam — a callable taking the run-input dict and
            returning raw actor items. Defaults to the real Apify call, so
            tests exercise parsing with no network (and no token needed).

    Returns:
        A list of ``Subreddit`` records, one per matched community with a
        usable name, in the actor's returned (relevance) order. Empty list if
        nothing matched.

    Raises:
        RuntimeError: if no Apify token is configured and no ``item_fetcher``
            was injected.
    """
    token = api_token or os.environ.get("APIFY_API_TOKEN")
    if item_fetcher is None and not token:
        raise RuntimeError(
            "APIFY_API_TOKEN is not set — needed by search_subreddits. "
            "Put it in config/.env."
        )

    run_input = {
        "searchTerms": [query],
        "searchCommunities": True,
        "searchPosts": False,
        "searchComments": False,
        "maxCommunitiesCount": max_communities,
        "searchSort": "relevance",
        "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
    }

    fetcher = item_fetcher or _make_apify_fetcher(actor_id, token, timeout_seconds)
    items = fetcher(run_input)

    subreddits: list[Subreddit] = []
    for item in items:
        name = item.get("name")
        if not name:
            continue
        raw = item.get("membersCount")
        if raw is None:
            members = 0
        else:
            try:
                members = int(raw)
            except (TypeError, ValueError):
                members = 0
        subreddits.append(
            Subreddit(
                name=name,
                title=item.get("title") or "",
                members=members,
                nsfw=bool(item.get("nsfw")),
            )
        )
    return subreddits


def _make_apify_fetcher(
    actor_id: str, api_token: str | None, timeout_seconds: float
) -> Callable[[dict], list[dict]]:
    """Build the default ``item_fetcher``: a real synchronous Apify actor call.

    Uses Apify's ``run-sync-get-dataset-items`` endpoint — starts the run,
    waits for it to finish, and returns the dataset items in one call. Same
    pattern as ``reddit_search._make_apify_fetcher``.
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
