"""Tests for EventExtractor — network-free via a fake AnthropicLLM stub."""

from src.monitor.schemas import DedupVerdict, TrendingEvent
from src.monitor.event_extractor import EventExtractor

class FakeLLM:
    """Minimal AnthropicLLM stub whose parse() always returns a fixed verdict."""

    def __init__(self, verdict: DedupVerdict) -> None:
        self._verdict = verdict

    def parse(self, prompt: str, response_model: type, **kwargs) -> DedupVerdict:
        return self._verdict


def _make_event(headline: str, reaction: str, score: float) -> TrendingEvent:
    return TrendingEvent(
        headline=headline,
        subreddit="test",
        url="https://reddit.com/test",
        reaction_sample=reaction,
        trendiness_score=score,
        virality_window_hours=24.0,
        raw_source_data={},
    )


# Two headlines about the same real-world event
EVENT_A = _make_event("Studio cancels beloved sequel", "I am devastated", 100.0)
EVENT_B = _make_event("Sequel officially dead after box office flop", "We deserved better", 50.0)

# Clearly unrelated event
EVENT_C = _make_event("Volcano erupts in Iceland", "Incredible footage", 30.0)


def test_duplicate_events_are_merged():
    verdict = DedupVerdict(is_same=True)
    extractor = EventExtractor(FakeLLM(verdict))
    result = extractor.extract([EVENT_A, EVENT_B])

    assert len(result) == 1
    assert "I am devastated" in result[0].reaction_sample
    assert "We deserved better" in result[0].reaction_sample

def test_different_events_both_survive():
    verdict = DedupVerdict(is_same=False)
    extractor = EventExtractor(FakeLLM(verdict))
    result = extractor.extract([EVENT_A, EVENT_C])

    assert len(result) == 2
    assert "I am devastated" in result[0].reaction_sample
    assert "Volcano erupts in Iceland" in result[1].headline


def test_output_sorted_and_capped():
    verdict = DedupVerdict(is_same=False)
    extractor = EventExtractor(FakeLLM(verdict))
    result = extractor.extract([EVENT_A, EVENT_B, EVENT_C], top_n=2)

    assert len(result) == 2
    assert result[0].trendiness_score >= result[1].trendiness_score