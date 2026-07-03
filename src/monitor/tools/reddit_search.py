"""LangGraph tool: search Reddit for posts/comments matching a free-text query.

Reuses the same Apify ``harshmaur/reddit-scraper`` actor and ``APIFY_API_TOKEN``
the Reddit cultural monitor already uses (see ``src/monitor/scraper.py``), but
in the actor's search mode (``searchTerms``) instead of subreddit-listing mode
(``startUrls``). The actor's input schema exposes search natively, so this is
the same provider/token/item-shape, just a different run-input — no new cost
surface beyond the existing Apify billing.

Run-input fields audited against the actor's full raw input schema (33
fields, pulled 2026-07-01) — every field this module sets/exposes matches a
real field name and type. See BUG-004 in ``bugs.md`` for a documented case
where a real, schema-valid field (``searchSort: "top"``) still didn't behave
as documented — schema presence alone doesn't guarantee correct behavior,
only a live probe does.
"""

import os
from typing import Callable

import httpx

from src.monitor.tools._types import ToolResult

_APIFY_BASE_URL = "https://api.apify.com/v2"
_DEFAULT_REDDIT_ACTOR = "harshmaur/reddit-scraper"

# https://apify.com/harshmaur/reddit-scraper: "From $2/1,000 results" (confirmed
# 2026-06-30 — the $0.001844/item figure used elsewhere in this codebase for a
# different actor does NOT apply here; verify per-actor, don't reuse).
_APIFY_COST_PER_ITEM = 0.002
_MAX_ESTIMATED_COST = 1.00


def estimate_cost(
    max_posts: int = 20,
    max_comments_per_post: int = 20,
    max_comments_count: int = 10,
) -> float:
    """Estimate the Apify cost (USD) a ``reddit_search`` call with these
    params would incur, using the same formula the per-call guard checks.

    Exposed so callers that need to reason about cost *before* calling
    (e.g. a cumulative per-run cap) use the same math the guard itself
    uses, instead of a second, driftable copy of the formula.
    """
    estimated_items = max_posts * (1 + max_comments_per_post) + max_comments_count
    return estimated_items * _APIFY_COST_PER_ITEM


def reddit_search(
    query: str,
    *,
    api_token: str | None = None,
    actor_id: str = _DEFAULT_REDDIT_ACTOR,
    max_posts: int = 5,
    max_comments_per_post: int = 20,
    max_comments_count: int = 10,
    within_community: str | None = None,
    include_nsfw: bool = False,
    timeout_seconds: float = 120.0,
    item_fetcher: Callable[[dict], list[dict]] | None = None,
) -> ToolResult:
    """Search Reddit for ``query`` and return matching posts/comments as one text blob.

    Args:
        query: Free-text search term (e.g. a topic name or character name).
        api_token: Apify API token. Defaults to the ``APIFY_API_TOKEN`` env var.
        actor_id: Apify actor id (slash form); tilde-encoded for the URL path.
        max_posts: Cap on matched posts (``maxPostsCount``) — NOT ``maxItems``,
            which this actor does not appear to honor in search mode (BUG-003:
            observed item counts ran ~10x over the old ``maxItems`` cap).
            Mirrors the field name ``ApifyRedditScraper`` already uses for
            listing mode.
        max_comments_per_post: Comments to crawl per matched post
            (``maxCommentsPerPost``), via the ``crawlCommentsPerPost`` pathway.
        max_comments_count: Cap on comments returned by the *separate*
            keyword-comment-search pathway (``maxCommentsCount``), active
            because ``searchComments=True`` below. Confirmed via the actor's
            raw README (2026-06-30) that this is a distinct pathway from
            ``crawlCommentsPerPost``/``maxCommentsPerPost`` with its own cap —
            previously left unset (silently defaulting to the actor's own
            default), which meant this pathway's item count wasn't reflected
            in the cost estimate below (same failure class as BUG-003:
            an actor input field silently doing something the code didn't
            account for). Default 10 mirrors the actor's own prior default,
            so behavior is unchanged unless a caller opts into a different
            value.
        within_community: Restrict the search to a single subreddit (actor
            field ``withinCommunity``, format ``"r/developers"``). ``None``
            (default) searches all of Reddit, matching current behavior —
            confirmed via the actor's raw input schema (2026-07-01) as the
            only community-scoping mechanism this actor exposes for keyword
            search; it takes exactly one subreddit, not a list, so scoping
            an arbitrary ``--topic`` call requires the caller to already
            know (or guess) which subreddit is relevant.
        include_nsfw: Whether to include posts flagged over-18 (actor field
            ``includeNSFW``). Previously left unset, silently relying on
            the actor's own unconfirmed default; now explicit, mirroring
            the same field ``ApifyRedditScraper`` already sets in
            ``scraper.py``.
        timeout_seconds: HTTP timeout for the synchronous actor run.
        item_fetcher: Optional seam for tests — a callable taking the run-input
            dict and returning the raw list of actor items. Defaults to the
            real Apify call, so tests can exercise the formatting with no
            network. Also bypasses the cost guard, same as the token check
            below — there is no real spend to guard against in tests.

    Returns:
        A ``ToolResult``. Its ``text`` is one block per matched post: a
        ``[POST | N upvotes]`` title line followed by its own comments as
        indented ``[COMMENT | N upvotes]`` lines, blocks separated by a blank
        line. Upvote counts are carried into the text deliberately: they are
        the only ground-truth "how many humans co-signed this" signal in the
        pipeline, and every LLM downstream (idea-fit gate, gap agent) weights
        consensus from them — dropping them (pre-2026-07-02 behavior) made an
        11-upvote joke thread and a 2,848-upvote wish-meme read as equally
        representative, causing a wrong gate kill. Items with no readable
        score fall back to a plain ``[POST]``/``[COMMENT]`` tag. Comments are
        grouped under their post via ``postId`` — the actor's raw item order
        interleaves posts and comments from different threads, so grouping
        (not print order) is what keeps a comment attributed to the right
        post. Blocks are ordered by post upvote count, highest first (BUG-009),
        so the downstream character-budget truncation in ``context_agent.gather``
        keeps the most co-signed reactions rather than whatever the actor's
        relevance order placed first; ties keep the actor's original order
        (stable sort). Empty string if nothing matched. Posts with no matched
        comments still get their own block. Its ``urls`` is each matched
        post's ``postUrl``, in the same order as the (now upvote-ranked) text
        blocks.

    Raises:
        RuntimeError: if no Apify token is configured and no ``item_fetcher``
            was injected, or if the estimated cost exceeds the $1.00 guard.
    """
    token = api_token or os.environ.get("APIFY_API_TOKEN")
    if item_fetcher is None and not token:
        raise RuntimeError(
            "APIFY_API_TOKEN is not set — needed by reddit_search. "
            "Put it in config/.env."
        )

    if item_fetcher is None:
        estimated_cost = estimate_cost(max_posts, max_comments_per_post, max_comments_count)
        if estimated_cost > _MAX_ESTIMATED_COST:
            raise RuntimeError(
                f"Refusing reddit_search: estimated cost ${estimated_cost:.2f} "
                f"(threshold ${_MAX_ESTIMATED_COST:.2f}). max_posts={max_posts} × "
                f"(1 + max_comments_per_post={max_comments_per_post}) + "
                f"max_comments_count={max_comments_count}. Pass smaller values."
            )

    run_input = {
        "searchTerms": [query],
        "searchPosts": True,
        "searchComments": True,
        "maxPostsCount": max_posts,
        "maxCommentsCount": max_comments_count,
        "crawlCommentsPerPost": True,
        "maxCommentsPerPost": max_comments_per_post,
        # Sort/time evidence chain (all live paid probes — this actor's
        # documented behavior repeatedly diverges from actual, so every value
        # here is probe-backed, not doc-trusted):
        # - 2026-07-01: "top" UNSCOPED ignores searchTerms entirely (returned
        #   r/pics/r/MadeMeSmile for a Wistoria query) → never use it unscoped.
        # - 2026-07-01: "top" + withinCommunity=r/Wistoria (tiny dedicated sub)
        #   worked — but only because in a dedicated sub, everything matches.
        # - 2026-07-02: "top" + withinCommunity=r/anime (mega sub) + no time
        #   window returned all-time mega-threads (Chainsaw Man Ep 1, zero
        #   Wistoria) for the same query family: term matching is loose
        #   (token-level, not phrase) and all-time upvote ranking buries any
        #   niche thread below maxPostsCount. The 07-01 scoped validation had
        #   overgeneralized from the dedicated-sub regime.
        # So: "relevance" always (weights full-term matches, the only sort
        # that survives both scoped regimes), plus a "month" time window —
        # this pipeline chases live reaction waves, so a thread older than a
        # month is never the target, and the window structurally excludes
        # historic mega-threads. Upvote-consensus signal is NOT lost by this:
        # it lives in the comments crawled from the found post
        # (crawlCommentsPerPost), not in the post-discovery ranking.
        "searchSort": "relevance",
        "searchTime": "month",
        "includeNSFW": include_nsfw,
        "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
    }
    if within_community:
        run_input["withinCommunity"] = within_community

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

    # Vote fields verified against real dataset items (2026-07-02, dataset
    # O1kl0zYKUbj7U1aJo): posts carry "score" + "upVotes", comments carry
    # "score" + "commentUpVotes". "score" is common to both; the per-type
    # field is the fallback.
    def _tag(kind: str, item: dict, fallback_field: str) -> str:
        votes = item.get("score")
        if votes is None:
            votes = item.get(fallback_field)
        if votes is None:
            return f"[{kind}]"
        return f"[{kind} | {votes} upvotes]"

    def _upvotes(item: dict, fallback_field: str) -> int:
        """Post's upvote count as an int for ranking (``score`` → fallback → 0).

        Mirrors ``_tag``'s field priority but returns a sortable number instead
        of a display string. Missing or uncoercible counts sink to 0, matching
        the ``ApifyRedditScraper._comment_upvotes`` convention in ``scraper.py``.
        """
        raw = item.get("score")
        if raw is None:
            raw = item.get(fallback_field)
        if raw is None:
            return 0
        try:
            return int(raw)
        except (TypeError, ValueError):
            return 0

    # One (upvotes, block, url) bundle per post so the upvote count stays glued
    # to its text and url through the sort below — sorting the blocks alone would
    # desync the parallel urls list.
    ranked: list[tuple[int, str, str | None]] = []
    for item in items:
        if item.get("dataType") != "post":
            continue
        bare_id = str(item.get("id") or "").removeprefix("t3_")
        post_lines = [f"{_tag('POST', item, 'upVotes')} {item.get('title') or ''}"]
        for comment in comments_by_post.get(bare_id, []):
            post_lines.append(
                f"  {_tag('COMMENT', comment, 'commentUpVotes')} {comment.get('body') or ''}"
            )
        ranked.append((_upvotes(item, "upVotes"), "\n".join(post_lines), item.get("postUrl")))

    # Rank posts by upvote consensus, highest first, so the downstream 2000-char
    # truncation in context_agent.gather() keeps the most co-signed reactions
    # instead of whatever relevance order the actor returned first (BUG-009: a
    # 15-upvote joke thread outranked a 244-upvote sincere thread and survived
    # the cut). Python's sort is stable, so ties keep the actor's original
    # relevance order. This ranks WITHIN one reddit_search call; ordering ACROSS
    # multiple accumulated calls is not handled here.
    ranked.sort(key=lambda bundle: bundle[0], reverse=True)

    blocks = [block for _, block, _ in ranked]
    urls = [url for _, _, url in ranked if url]

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
