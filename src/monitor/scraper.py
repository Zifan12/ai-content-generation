"""Reddit cultural monitor — scrapes hot posts from a set of subreddits.

Wraps a praw.Reddit client (injected, never constructed here) so the class is
fully testable without a network: pass a fake client in tests, pass the real
praw.Reddit instance at the call site in production.

virality_window_hours is hardcoded to 24.0 in v1 — a signal refinement (e.g.
post-age delta or Reddit velocity API) is a future improvement.
"""

import os
from typing import Any, Callable

import httpx

from src.monitor.schemas import TrendingEvent

_VIRALITY_WINDOW_HOURS_V1 = 24.0

_APIFY_BASE_URL = "https://api.apify.com/v2"
_DEFAULT_REDDIT_ACTOR = "harshmaur/reddit-scraper"


class RedditScraper:
    """Fetch trending posts from one or more subreddits and return TrendingEvent objects.

    Args:
        reddit_client: A praw.Reddit instance (or any compatible stub). Must
            support ``.subreddit(name).hot(limit=N)`` yielding submission objects
            with ``.title``, ``.score``, ``.url``, and ``.comments``. ``.comments``
            is a praw ``CommentForest``: it may contain ``MoreComments`` placeholder
            objects (which have no ``.body``), so we call ``replace_more(limit=0)``
            to drop them with zero extra API requests before reading comment bodies.
        subreddits: Names of subreddits to monitor (e.g. ``["television", "movies"]``).
        post_limit: Maximum number of hot posts to fetch per subreddit.
        comment_limit: Maximum number of top-level comments to include in
            ``reaction_sample`` per post.

    Returns from fetch():
        A flat list of ``TrendingEvent`` objects, one per post across all
        subreddits. Order is subreddit-then-post (television posts, then movies
        posts, etc.). Posts with zero score are included — filtering is the
        caller's responsibility.
    """

    def __init__(
        self,
        reddit_client,
        subreddits: list[str],
        post_limit: int = 25,
        comment_limit: int = 20,
    ) -> None:
        self._client = reddit_client
        self._subreddits = subreddits
        self._post_limit = post_limit
        self._comment_limit = comment_limit

    def fetch(self) -> list[TrendingEvent]:
        """Fetch hot posts from all configured subreddits and return TrendingEvent objects."""
        events: list[TrendingEvent] = []
        for name in self._subreddits:
            sub = self._client.subreddit(name)
            for post in sub.hot(limit=self._post_limit):
                post.comments.replace_more(limit=0)
                comments = list(post.comments)[: self._comment_limit]
                reaction_sample = "\n".join(c.body for c in comments)
                events.append(
                    TrendingEvent(
                        headline=post.title,
                        subreddit=name,
                        url=post.url,
                        reaction_sample=reaction_sample,
                        trendiness_score=float(post.score),
                        virality_window_hours=_VIRALITY_WINDOW_HOURS_V1,
                        origin="scraped",
                        raw_source_data={
                            "title": post.title,
                            "score": post.score,
                            "url": post.url,
                            "subreddit": name,
                        },
                    )
                )
        return events


class ApifyRedditScraper:
    """Fetch trending Reddit posts (with comments) via the Apify ``harshmaur/reddit-scraper`` actor.

    This is the v1 replacement for ``RedditScraper``. Reddit shut down its public
    ``.json`` endpoints (May 2026) and gates self-service API-key creation, so we
    source the same data through Apify — the same provider and ``APIFY_API_TOKEN``
    the TikTok scraper already uses. The downstream contract is identical:
    ``fetch()`` returns a flat ``list[TrendingEvent]``, so nothing in the monitor
    pipeline changes.

    The actor returns one flat list mixing posts and comments, distinguished by a
    ``dataType`` field (``"post"`` / ``"comment"``). Comments link back to their
    post via ``postId`` in Reddit fullname form (e.g. ``"t3_1uggvux"``); the
    corresponding post's ``id`` is the bare form (e.g. ``"1uggvux"``). This class
    strips the ``t3_`` prefix when bucketing so the join is consistent. Posts are
    preserved in source (hot) order.

    Args:
        subreddits: Subreddit names to scrape (e.g. ``["all", "popular"]``). Each
            becomes a ``https://www.reddit.com/r/<name>/<sort>/`` start URL.
        api_token: Apify API token. Defaults to the ``APIFY_API_TOKEN`` env var.
        actor_id: Apify actor id (slash form); tilde-encoded for the URL path.
        max_posts: Cap on posts saved **per start URL** (actor's ``maxPostsCount``).
            IMPORTANT: this is per-URL, not a total — scraping 10 subreddits
            with max_posts=10 yields up to 100 posts. Billed at ~$0.001844
            per returned item (post + every fetched comment), so total cost =
            ``len(subreddits) × max_posts × (1 + fetch_comments_per_post)``
            × $0.001844. Use small max_posts/max_comments for probe runs.
        fetch_comments_per_post: How many comments to pull per post from the actor
            (``maxCommentsPerPost``). Set generously (default 50): the actor has NO
            top-comment sort and truncates in default traversal order, so the only
            way to be sure the highest-upvoted comments are present is to fetch wide.
        top_comments_in_sample: After fetching, keep only this many of each post's
            TOP-LEVEL comments, ranked by ``commentUpVotes`` descending, for the
            ``reaction_sample`` (default 8). This is what grounds the gap agent —
            the loudest reactions, not a default-ordered slice.
        sort: Listing sort used in the start URL (``"hot"``, ``"new"``, ``"top"``).
        include_nsfw: Whether to include posts flagged over-18.
        timeout_seconds: HTTP timeout for the synchronous actor run (scraping
            comments can take a minute or two).
        item_fetcher: Optional seam for tests — a callable taking the run-input
            dict and returning the raw list of actor items. Defaults to the real
            Apify call, so tests can exercise the mapping with no network.

    Returns from fetch():
        A ``list[TrendingEvent]``, one per scraped post. Posts with no matching
        comments yield an empty ``reaction_sample`` (filtering is the caller's job).
    """

    def __init__(
        self,
        subreddits: list[str],
        *,
        api_token: str | None = None,
        actor_id: str = _DEFAULT_REDDIT_ACTOR,
        max_posts: int = 25,
        fetch_comments_per_post: int = 50,
        top_comments_in_sample: int = 8,
        sort: str = "hot",
        include_nsfw: bool = False,
        timeout_seconds: float = 300.0,
        item_fetcher: Callable[[dict], list[dict]] | None = None,
    ) -> None:
        self._subreddits = subreddits
        self._api_token = api_token or os.environ.get("APIFY_API_TOKEN")
        self._actor_id = actor_id
        self._max_posts = max_posts
        self._fetch_comments_per_post = fetch_comments_per_post
        self._top_comments_in_sample = top_comments_in_sample
        self._sort = sort
        self._include_nsfw = include_nsfw
        self._timeout_seconds = timeout_seconds
        self._item_fetcher = item_fetcher or self._fetch_from_apify

    def fetch(self) -> list[TrendingEvent]:
        """Run the actor, regroup the flat post/comment list, and return TrendingEvents."""
        raw_items = self._item_fetcher(self._build_run_input())
        return self._items_to_events(raw_items)

    def _build_run_input(self) -> dict[str, Any]:
        """Build the actor run-input from the configured subreddits and limits."""
        start_urls = [
            {"url": f"https://www.reddit.com/r/{self._clean_subreddit(name)}/{self._sort}/"}
            for name in self._subreddits
        ]
        return {
            "startUrls": start_urls,
            "crawlCommentsPerPost": True,
            "maxPostsCount": self._max_posts,
            "maxCommentsPerPost": self._fetch_comments_per_post,
            "includeNSFW": self._include_nsfw,
            "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        }

    @staticmethod
    def _clean_subreddit(name: str) -> str:
        """Normalize a subreddit name to its bare form (strip ``r/`` prefix and slashes)."""
        cleaned = name.strip().strip("/")
        if cleaned.lower().startswith("r/"):
            cleaned = cleaned[2:]
        return cleaned

    def _fetch_from_apify(self, run_input: dict[str, Any]) -> list[dict]:
        """Run the actor synchronously and return its dataset items (the raw flat list).

        Uses Apify's ``run-sync-get-dataset-items`` endpoint, which starts the run,
        waits for it to finish, and returns the dataset items in one call.

        Raises:
            RuntimeError: if no Apify token is configured.
            httpx.HTTPStatusError: if the actor run request fails.
        """
        if not self._api_token:
            raise RuntimeError(
                "APIFY_API_TOKEN is not set — needed by ApifyRedditScraper. "
                "Put it in config/.env."
            )
        actor_path = self._actor_id.replace("/", "~")
        url = f"{_APIFY_BASE_URL}/acts/{actor_path}/run-sync-get-dataset-items"
        # Sync by design — CLI-only in v1; move to httpx.AsyncClient if this is
        # ever called from a FastAPI route or LangGraph tool.
        response = httpx.post(
            url,
            params={"token": self._api_token},
            json=run_input,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def _items_to_events(self, items: list[dict]) -> list[TrendingEvent]:
        """Regroup the flat post/comment list into one TrendingEvent per post.

        Comments are bucketed by their ``postId`` (which matches a post's ``id``),
        then each post's comment ``body`` texts are joined into ``reaction_sample``.
        ``trendiness_score`` prefers the post ``score`` and falls back to
        ``upVotes`` (both are best-effort from the actor and may be 0).
        """
        comments_by_post: dict[str, list[dict]] = {}
        for item in items:
            if item.get("dataType") != "comment":
                continue
            post_id = item.get("postId")
            if post_id is None:
                continue
            # Actor returns postId as Reddit fullname ("t3_xxxx"); post id is bare ("xxxx").
            bare_post_id = str(post_id).removeprefix("t3_")
            comments_by_post.setdefault(bare_post_id, []).append(item)

        events: list[TrendingEvent] = []
        for item in items:
            if item.get("dataType") != "post":
                continue

            bare_id = str(item.get("id") or "").removeprefix("t3_")
            all_comments = comments_by_post.get(bare_id, [])
            ranked_comments = self._top_comments(all_comments)
            reaction_sample = "\n".join(
                str(c.get("body") or "") for c in ranked_comments
            ).strip()

            raw_score = item.get("score")
            if raw_score is None:
                raw_score = item.get("upVotes")
            try:
                trendiness_score = float(raw_score or 0)
            except (ValueError, TypeError):
                trendiness_score = 0.0

            subreddit = item.get("parsedCommunityName") or self._clean_subreddit(
                item.get("communityName") or ""
            )

            events.append(
                TrendingEvent(
                    headline=item.get("title") or "",
                    subreddit=subreddit,
                    url=item.get("postUrl") or "",
                    reaction_sample=reaction_sample,
                    trendiness_score=trendiness_score,
                    virality_window_hours=_VIRALITY_WINDOW_HOURS_V1,
                    origin="scraped",
                    raw_source_data={
                        "post": item,
                        "comment_count": len(all_comments),
                        "comments_kept": len(ranked_comments),
                    },
                )
            )
        return events

    @staticmethod
    def _comment_upvotes(comment: dict) -> int:
        """Coerce a comment's upvote count to int (``commentUpVotes`` → ``score`` → 0).

        The actor's vote fields are best-effort and may be null or string-typed
        across runs, so coerce defensively and treat anything unparseable as 0.
        """
        raw = comment.get("commentUpVotes")
        if raw is None:
            raw = comment.get("score")
        try:
            return int(raw or 0)
        except (ValueError, TypeError):
            return 0

    def _top_comments(self, comments: list[dict]) -> list[dict]:
        """Pick the most-upvoted top-level comments for the reaction sample.

        The actor returns up to ``fetch_comments_per_post`` comments per post in a
        default traversal order (NOT ranked by score), mixing top-level comments
        and nested replies (``depth`` > 0). Grounding the gap agent on a default
        slice risks feeding it unrepresentative reactions, so we:

        1. keep only top-level comments (``depth`` 0 or absent — replies are
           sub-arguments, noise for "what does the audience want"),
        2. sort by upvotes descending,
        3. return the top ``top_comments_in_sample``.
        """
        top_level = [c for c in comments if (c.get("depth") or 0) == 0]
        top_level.sort(key=self._comment_upvotes, reverse=True)
        return top_level[: self._top_comments_in_sample]
