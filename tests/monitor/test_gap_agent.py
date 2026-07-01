from src.monitor.gap_agent import GapAgent
from src.monitor.schemas import (
    ContextBundle,
    GapAnalysis,
    GapType,
    TrendingEvent,
)

SAMPLE_EVENT = TrendingEvent(
    headline="Dragon spotted circling Tokyo Tower at dawn",
    subreddit="interestingasfuck",
    url="https://reddit.com/r/interestingasfuck/comments/abc123",
    reaction_sample="Top comment: 'I wish we got to see it actually breathe fire.' "
    "Reply: 'They cut away right before the good part, classic.'",
    trendiness_score=0.92,
    virality_window_hours=18.0,
    raw_source_data={},
    origin="scraped",
)

class FakeLLM:
    def __init__(self, analysis: GapAnalysis) -> None:
        self._analysis = analysis
       

    def parse(self, prompt: str, response_model: type, **kwargs) -> GapAnalysis:
        self.prompt = prompt
        return self._analysis


def _sample_analysis() -> GapAnalysis:
    return GapAnalysis(
        dominant_emotion="longing",
        audience_want="to see the dragon actually breathe fire",
        gap_type=GapType.alternate_reality,
        producibility_score=0.8,
        virality_window_hours=18.0,
        reasoning="The crowd was teased a payoff the footage never delivered.",
    )


def _sample_bundle() -> ContextBundle:
    return ContextBundle(
        reaction_sample="I wish we saw the dragon breathe fire",
        summary="Tokyo residents report a dragon sighting at dawn; the footage cuts before the fire breath.",
        key_moments=["dragon first appears at 06:14 JST", "camera cuts away before fire breath"],
        references=["https://news.example.com/dragon-tokyo", "https://reddit.com/r/tokyo/dragon"],
        sources=["tavily", "reddit"],
    )


def test_analysis():
    analysis = _sample_analysis()

    fake = FakeLLM(analysis=analysis)
    agent = GapAgent(llm=fake)
    result = agent.analyze(SAMPLE_EVENT)

    assert result == analysis
    assert "Dragon spotted circling Tokyo Tower" in fake.prompt


def test_analyze_without_bundle_has_no_context_block():
    """Regression: bundle=None path must not inject a <context> block.

    Asserts the structural invariant (no <context> tag) rather than a brittle
    full-prompt equality check.
    """
    fake = FakeLLM(analysis=_sample_analysis())
    agent = GapAgent(llm=fake)

    agent.analyze(SAMPLE_EVENT, bundle=None)

    assert "<context>" not in fake.prompt
    assert "</context>" not in fake.prompt
    assert "<event_headline>" in fake.prompt
    assert "<audience_reaction>" in fake.prompt


def test_analyze_with_bundle_injects_context_block():
    """bundle provided -> prompt contains a <context> block with summary,
    key_moments, and references, alongside the unchanged event blocks."""
    fake = FakeLLM(analysis=_sample_analysis())
    agent = GapAgent(llm=fake)
    bundle = _sample_bundle()

    agent.analyze(SAMPLE_EVENT, bundle=bundle)

    assert "<context>" in fake.prompt and "</context>" in fake.prompt
    assert bundle.summary in fake.prompt
    for moment in bundle.key_moments:
        assert moment in fake.prompt, f"key_moment {moment!r} missing from prompt"
    for ref in bundle.references:
        assert ref in fake.prompt, f"reference {ref!r} missing from prompt"
    assert "<event_headline>" in fake.prompt
    assert "<audience_reaction>" in fake.prompt
    
