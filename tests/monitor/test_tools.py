import pytest
from pydantic import ValidationError

from src.monitor.schemas import ContextBundle, TrendingEvent
from src.monitor.tools import reddit_search, tavily_search

fake_bundle = ContextBundle(
    reaction_sample="people are losing it over the ending, comments full of all-caps disbelief",
    summary="Show X's season finale killed off the lead character, fandom split between betrayal and praise for the bold move",
    key_moments=["lead character death at minute 42", "showrunner confirms no resurrection planned"],
    references=["https://reddit.com/r/television/comments/abc123"],
    sources=["reddit_search", "tavily"],
)


def _make_trending_event(**overrides) -> TrendingEvent:
    fields = dict(
        headline="Show X's lead character dies in the finale",
        subreddit="television",
        url="https://reddit.com/r/television/comments/abc123",
        reaction_sample="people are losing it over the ending",
        trendiness_score=500.0,
        virality_window_hours=24.0,
        raw_source_data={},
        origin="scraped",
    )
    fields.update(overrides)
    return TrendingEvent(**fields)


def test_context_bundle_round_trip():
    bundle = fake_bundle

    assert bundle.reaction_sample == "people are losing it over the ending, comments full of all-caps disbelief"
    assert bundle.summary == "Show X's season finale killed off the lead character, fandom split between betrayal and praise for the bold move"
    assert bundle.key_moments == ["lead character death at minute 42", "showrunner confirms no resurrection planned"]
    assert bundle.references == ["https://reddit.com/r/television/comments/abc123"]
    assert bundle.sources == ["reddit_search", "tavily"]


def test_context_bundle_extra_field_DNE():
    with pytest.raises(ValidationError):
        ContextBundle(
            reaction_sample="people are losing it over the ending",
            summary="Show X's lead character dies in the finale",
            key_moments=["lead character death at minute 42"],
            references=["https://reddit.com/r/television/comments/abc123"],
            sources=["reddit_search", "tavily"],
            mood="cheerful",
        )


def test_trending_event_origin_required():
    fields = dict(
        headline="Show X's lead character dies in the finale",
        subreddit="television",
        url="https://reddit.com/r/television/comments/abc123",
        reaction_sample="people are losing it over the ending",
        trendiness_score=500.0,
        virality_window_hours=24.0,
        raw_source_data={},
    )
    with pytest.raises(ValidationError):
        TrendingEvent(**fields)


def test_trending_event_origin_rejects_invalid_value():
    with pytest.raises(ValidationError):
        _make_trending_event(origin="garbage")


def test_trending_event_origin_accepts_valid_values():
    scraped = _make_trending_event(origin="scraped")
    manual = _make_trending_event(origin="manual")

    assert scraped.origin == "scraped"
    assert manual.origin == "manual"


def test_reddit_search_formats_items():
    result = reddit_search(
        "Wistoria",
        item_fetcher=lambda run_input: [
            {"dataType": "post", "id": "t3_abc", "title": "test", "postUrl": "https://reddit.com/abc"}
        ],
    )

    assert "test" in result.text
    assert result.urls == ["https://reddit.com/abc"]


def test_reddit_search_carries_upvote_counts_into_text():
    """Regression for the 2026-07-02 wrong gate kill: upvote counts were
    stripped at formatting, so the gate weighted an 11-upvote joke thread and
    a 2,848-upvote wish-meme identically. Post and comment lines must carry
    their scores; items with no readable score fall back to a bare tag."""
    result = reddit_search(
        "Wistoria",
        item_fetcher=lambda run_input: [
            {
                "dataType": "post",
                "id": "t3_meme",
                "title": "The ultimate Albis experience simulator",
                "postUrl": "https://reddit.com/meme",
                "score": 2848,
            },
            {
                "dataType": "comment",
                "postId": "t3_meme",
                "body": "meant to be",
                "commentUpVotes": 9,
            },
            {
                "dataType": "post",
                "id": "t3_scoreless",
                "title": "no votes field",
                "postUrl": "https://reddit.com/scoreless",
            },
        ],
    )

    assert "[POST | 2848 upvotes] The ultimate Albis experience simulator" in result.text
    assert "[COMMENT | 9 upvotes] meant to be" in result.text
    assert "[POST] no votes field" in result.text


def test_reddit_search_omits_within_community_by_default():
    captured = {}

    def fake_fetcher(run_input):
        captured.update(run_input)
        return []

    reddit_search("Wistoria", item_fetcher=fake_fetcher)

    assert "withinCommunity" not in captured
    assert captured["includeNSFW"] is False


def test_reddit_search_sets_within_community_when_given():
    captured = {}

    def fake_fetcher(run_input):
        captured.update(run_input)
        return []

    reddit_search("Wistoria", within_community="r/Wistoria", item_fetcher=fake_fetcher)

    assert captured["withinCommunity"] == "r/Wistoria"


def test_reddit_search_sort_relevance_and_month_window_unscoped():
    captured = {}

    def fake_fetcher(run_input):
        captured.update(run_input)
        return []

    reddit_search("Wistoria", item_fetcher=fake_fetcher)

    assert captured["searchSort"] == "relevance"
    assert captured["searchTime"] == "month"


def test_reddit_search_sort_relevance_and_month_window_scoped():
    """Regression for the 2026-07-02 mega-sub failure: scoped searches used
    "top" with no time window, which returned all-time megathreads (Chainsaw
    Man Ep 1) instead of the niche on-topic thread. Scoped and unscoped now
    both pin relevance + a month window."""
    captured = {}

    def fake_fetcher(run_input):
        captured.update(run_input)
        return []

    reddit_search("Wistoria", within_community="r/anime", item_fetcher=fake_fetcher)

    assert captured["searchSort"] == "relevance"
    assert captured["searchTime"] == "month"


class _FakeTavilyClient:
    def search(self, query: str, max_results: int = 5) -> dict:
        return {
            "results": [
                {
                    "title": "Wistoria fan wiki",
                    "url": "https://example.com/wistoria",
                    "content": "Wistoria is a fantasy anime about a wand-crafting student.",
                }
            ]
        }


def test_tavily_search_formats_results():
    result = tavily_search("Wistoria", client=_FakeTavilyClient())

    assert "Wistoria fan wiki" in result.text
    assert "https://example.com/wistoria" in result.text
    assert "wand-crafting student" in result.text
    assert result.urls == ["https://example.com/wistoria"]