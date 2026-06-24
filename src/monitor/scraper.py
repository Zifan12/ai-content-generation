"""Reddit cultural monitor — scrapes hot posts from a set of subreddits.

Wraps a praw.Reddit client (injected, never constructed here) so the class is
fully testable without a network: pass a fake client in tests, pass the real
praw.Reddit instance at the call site in production.

virality_window_hours is hardcoded to 24.0 in v1 — a signal refinement (e.g.
post-age delta or Reddit velocity API) is a future improvement.
"""

from src.monitor.schemas import TrendingEvent

_VIRALITY_WINDOW_HOURS_V1 = 24.0


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
                        raw_source_data={
                            "title": post.title,
                            "score": post.score,
                            "url": post.url,
                            "subreddit": name,
                        },
                    )
                )
        return events
