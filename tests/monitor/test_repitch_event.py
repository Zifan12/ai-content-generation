"""Unit tests for repitch_event.py's stored-bundle and pinned-gap loading."""

from datetime import datetime, timezone

from src.models.trending_event import TrendingEventRecord
from src.monitor.schemas import ContextBundle, GapAnalysis
from scripts.repitch_event import (
    _PinnedGapAgent,
    load_bundle,
    load_event,
    load_pinned_gap,
)


def _record(event_id, context_bundle, dominant_emotion=None, audience_want=None):
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
        dominant_emotion=dominant_emotion,
        audience_want=audience_want,
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


def test_load_pinned_gap_reuses_stored_read():
    """The audience read is a per-event fact — a re-pitch must reuse it, not
    re-roll it (2026-07-16: six runs of one thread got six different reads)."""
    record = _record(
        17,
        context_bundle=None,
        dominant_emotion="glee",
        audience_want="Elfaria successfully keeps Will (intimate comedic)",
    )

    class FakeDB:
        def get(self, model, event_id):
            return record

    gap = load_pinned_gap(FakeDB(), 17)
    assert isinstance(gap, GapAnalysis)
    assert gap.dominant_emotion == "glee"
    assert "keeps Will" in gap.audience_want


def test_load_pinned_gap_none_when_never_analyzed():
    """A row persisted by the flagged-unresolved path has no stored read —
    the caller falls back to a live gap analyze."""
    record = _record(9, context_bundle=None)

    class FakeDB:
        def get(self, model, event_id):
            return record

    assert load_pinned_gap(FakeDB(), 9) is None


def test_pinned_gap_agent_returns_stored_read_and_ignores_bundle():
    gap = GapAnalysis(
        dominant_emotion="glee",
        audience_want="w",
        evidence_quotes=[],
        reasoning="(pinned)",
    )
    agent = _PinnedGapAgent(gap)
    assert agent.analyze(event=None, bundle=None) is gap
    assert agent.analyze(event=None, bundle="anything") is gap
