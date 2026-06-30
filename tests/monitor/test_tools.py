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
    
    result = reddit_search("Wistoria", item_fetcher=lambda run_input: [{"dataType": "post", "title": "test"}])

    assert "test" in result


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

    assert "Wistoria fan wiki" in result
    assert "https://example.com/wistoria" in result
    assert "wand-crafting student" in result