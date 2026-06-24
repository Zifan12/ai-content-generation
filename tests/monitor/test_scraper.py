"""Tests for RedditScraper — all network-free via a fake praw client stub."""

from src.monitor.scraper import RedditScraper
from src.monitor.schemas import TrendingEvent


class FakeComment:
    def __init__(self, body: str) -> None:
        self.body = body


class FakeMoreComments:
    """Stand-in for praw's MoreComments placeholder — deliberately has no .body.

    Iterating a real CommentForest yields these mixed in with real comments;
    reading ``.body`` on one raises AttributeError. The scraper must call
    ``replace_more(limit=0)`` to strip them first, so we keep one here to guard
    that the scraper actually does.
    """


class FakeCommentForest:
    """Minimal praw CommentForest stub.

    Holds a mix of FakeComment and FakeMoreComments. ``replace_more(limit=0)``
    removes the placeholders in place (mirroring praw's zero-request strip);
    iterating before that call exposes the placeholders, just like real praw.
    """

    def __init__(self, comments: list) -> None:
        self._comments = list(comments)

    def replace_more(self, *, limit: int | None = 32, threshold: int = 0) -> list:
        removed = [c for c in self._comments if isinstance(c, FakeMoreComments)]
        if limit == 0:
            self._comments = [c for c in self._comments if not isinstance(c, FakeMoreComments)]
            return []
        return removed

    def __iter__(self):
        return iter(self._comments)


class FakeSubmission:
    def __init__(self, title: str, score: int, url: str, comments: list) -> None:
        self.title = title
        self.score = score
        self.url = url
        self.comments = FakeCommentForest(comments)


class FakeSubreddit:
    def __init__(self, submissions: list[FakeSubmission]) -> None:
        self._submissions = submissions

    def hot(self, limit: int) -> list[FakeSubmission]:
        return self._submissions[:limit]


class FakeReddit:
    """Minimal praw.Reddit stub — only .subreddit(name).hot(limit) is used."""

    def __init__(self, subs: dict[str, list[FakeSubmission]]) -> None:
        self._subs = subs

    def subreddit(self, name: str) -> FakeSubreddit:
        return FakeSubreddit(self._subs.get(name, []))


def _make_client() -> FakeReddit:
    comments = [
        FakeMoreComments(),  # first, so it lands inside the slice and trips if not stripped
        FakeComment("I can't believe they did that"),
        FakeComment("This is outrageous"),
    ]
    submission = FakeSubmission(
        title="Fans furious over Boys S5 finale letdown",
        score=42000,
        url="https://reddit.com/r/television/comments/abc123",
        comments=comments,
    )
    return FakeReddit({"television": [submission]})


def test_fetch_returns_trending_events():
    """fetch() returns one TrendingEvent per post across all subreddits."""
    client = _make_client()
    scraper = RedditScraper(client, subreddits=["television"], post_limit=5, comment_limit=2)

    results = scraper.fetch()

    assert len(results) == 1
    assert isinstance(results[0], TrendingEvent)


def test_trending_event_headline_matches_post_title():
    client = _make_client()
    scraper = RedditScraper(client, subreddits=["television"], post_limit=5, comment_limit=2)

    event = scraper.fetch()[0]

    assert event.headline == "Fans furious over Boys S5 finale letdown"


def test_trending_event_reaction_sample_contains_comments():
    client = _make_client()
    scraper = RedditScraper(client, subreddits=["television"], post_limit=5, comment_limit=2)

    event = scraper.fetch()[0]

    assert "I can't believe they did that" in event.reaction_sample
    assert "This is outrageous" in event.reaction_sample


def test_trending_event_trendiness_score_is_positive_float():
    client = _make_client()
    scraper = RedditScraper(client, subreddits=["television"], post_limit=5, comment_limit=2)

    event = scraper.fetch()[0]

    assert isinstance(event.trendiness_score, float)
    assert event.trendiness_score > 0


def test_trending_event_virality_window_is_positive():
    client = _make_client()
    scraper = RedditScraper(client, subreddits=["television"], post_limit=5, comment_limit=2)

    event = scraper.fetch()[0]

    assert event.virality_window_hours > 0


def test_multiple_subreddits_aggregated():
    """Events from multiple subreddits are all returned in one flat list."""
    comments = [FakeMoreComments(), FakeComment("wow")]
    client = FakeReddit({
        "television": [FakeSubmission("Post A", 1000, "https://reddit.com/a", comments)],
        "movies": [FakeSubmission("Post B", 2000, "https://reddit.com/b", comments)],
    })
    scraper = RedditScraper(client, subreddits=["television", "movies"], post_limit=5, comment_limit=1)

    results = scraper.fetch()

    assert len(results) == 2
    headlines = {e.headline for e in results}
    assert "Post A" in headlines
    assert "Post B" in headlines


def test_subreddit_field_is_set():
    client = _make_client()
    scraper = RedditScraper(client, subreddits=["television"], post_limit=5, comment_limit=2)

    event = scraper.fetch()[0]

    assert event.subreddit == "television"
