"""Unit tests for repitch_event.py's stored-bundle loading."""

from datetime import datetime, timezone

from src.models.trending_event import TrendingEventRecord
from src.monitor.schemas import ContextBundle
from scripts.repitch_event import load_event, load_bundle


def _record(event_id, context_bundle):
    return TrendingEventRecord(
        id=event_id,
        run_at=datetime.now(timezone.utc),
        source="reddit",
        headline="Test",
        url="https://x.com",
        reaction_sample="text",
        trendiness_score=1.0,
        virality_window_hours=24.0,
        context_bundle=context_bundle,
    )


def test_load_event_unchanged():
    record = _record(8, context_bundle={
        "reaction_sample": "text", "summary": "s", "key_moments": [],
        "references": [], "sources": [], "apify_cost_estimate": 0.5,
        "unresolved_facts": ["the age question"],
    })

    class FakeDB:
        def get(self, model, event_id):
            return record

    event = load_event(FakeDB(), 8)
    assert event.headline == "Test"


def test_load_bundle_reconstructs_context_bundle():
    record = _record(8, context_bundle={
        "reaction_sample": "text", "summary": "s", "key_moments": [],
        "references": [], "sources": [], "apify_cost_estimate": 0.5,
        "unresolved_facts": ["the age question"],
    })

    class FakeDB:
        def get(self, model, event_id):
            return record

    bundle = load_bundle(FakeDB(), 8)
    assert isinstance(bundle, ContextBundle)
    assert bundle.unresolved_facts == ["the age question"]


def test_load_bundle_none_when_no_stored_bundle():
    record = _record(9, context_bundle=None)

    class FakeDB:
        def get(self, model, event_id):
            return record

    assert load_bundle(FakeDB(), 9) is None
