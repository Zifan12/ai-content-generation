

from src.monitor.angle_pitcher import AnglePitcher
from src.monitor.schemas import (
    AnglePitch,
    AnglePitchSlate,
    ContextBundle,
    GapAnalysis,
    GapType,
    RenderBackend,
    TrendingEvent,
)
from src.rag.embedder import TextEmbedder

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

SAMPLE_GAP = GapAnalysis(
    dominant_emotion="longing",
    audience_want="to see the dragon actually breathe fire",
    gap_type=GapType.alternate_reality,
    producibility_score=0.8,
    virality_window_hours=18.0,
    reasoning="The crowd was teased a payoff the footage never delivered.",
)

SAMPLE_SLATE = AnglePitchSlate(
    angles=[
        AnglePitch(
            take="The dragon finally breathes fire over Tokyo Tower at dawn",
            format_description="Single wide aerial shot, slow push-in as flame erupts",
            render_backend=RenderBackend.visual_satire,
            estimated_cost_credits=24.0,
            gap_satisfaction_rationale="Shows the fire-breath payoff fans were denied",
            legal_flag=False,
        ),
        AnglePitch(
            take="Breaking news helicopter footage captures the dragon's fire breath",
            format_description="Mock news B-roll, shaky helicopter POV, lower-third chyron",
            render_backend=RenderBackend.commentary_voiceover,
            estimated_cost_credits=24.0,
            gap_satisfaction_rationale="Delivers the climax through a documentary news frame",
            legal_flag=False,
        ),
        AnglePitch(
            take="A-list actor watches the dragon breathe fire from a rooftop",
            format_description="Split-screen: celebrity reaction face + dragon fire wide shot",
            render_backend=RenderBackend.narrative_alt,
            estimated_cost_credits=30.0,
            gap_satisfaction_rationale="Pairs the wish-fulfillment with a recognizable reaction",
            legal_flag=True,
        ),
    ]
)

class FakeLLM:
    def __init__(self, slate: AnglePitchSlate) -> None:
        self._slate = slate

    def parse(self, prompt: str, response_model: type, **kwargs) -> AnglePitchSlate:
        self.prompt = prompt
        return self._slate


class FakeEmbedder(TextEmbedder):
    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts = texts
        return [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]

    @property
    def dim(self) -> int:
        return 1024

    @property
    def model_name(self) -> str:
        return "fake-embedder"


def test_pitch_returns_slate_and_calls_embedder():
    fake_llm = FakeLLM(slate=SAMPLE_SLATE)
    fake_embedder = FakeEmbedder()
    pitcher = AnglePitcher(llm=fake_llm, embedder=fake_embedder)

    result = pitcher.pitch(SAMPLE_EVENT, SAMPLE_GAP)

    assert len(result.angles) == 3
    for angle in result.angles:
        assert isinstance(angle.render_backend, RenderBackend)
    assert fake_embedder.texts


def _sample_bundle() -> ContextBundle:
    return ContextBundle(
        reaction_sample="I wish we saw the dragon breathe fire",
        summary="Tokyo residents report a dragon sighting at dawn; the footage cuts before the fire breath.",
        key_moments=["dragon first appears at 06:14 JST", "camera cuts away before fire breath"],
        references=["https://news.example.com/dragon-tokyo", "https://reddit.com/r/tokyo/dragon"],
        sources=["tavily", "reddit"],
    )


def test_pitch_without_bundle_has_no_context_block():
    """Regression: bundle=None path must not inject a <context> block."""
    fake_llm = FakeLLM(slate=SAMPLE_SLATE)
    fake_embedder = FakeEmbedder()
    pitcher = AnglePitcher(llm=fake_llm, embedder=fake_embedder)

    pitcher.pitch(SAMPLE_EVENT, SAMPLE_GAP, bundle=None)

    assert "<context>" not in fake_llm.prompt
    assert "</context>" not in fake_llm.prompt
    assert "<event>" in fake_llm.prompt
    assert "<gap>" in fake_llm.prompt


def test_pitch_with_bundle_injects_context_block():
    """bundle provided -> prompt contains a <context> block with summary,
    key_moments, and references, alongside the unchanged event+gap blocks."""
    fake_llm = FakeLLM(slate=SAMPLE_SLATE)
    fake_embedder = FakeEmbedder()
    pitcher = AnglePitcher(llm=fake_llm, embedder=fake_embedder)
    bundle = _sample_bundle()

    pitcher.pitch(SAMPLE_EVENT, SAMPLE_GAP, bundle=bundle)

    assert "<context>" in fake_llm.prompt and "</context>" in fake_llm.prompt
    assert bundle.summary in fake_llm.prompt
    for moment in bundle.key_moments:
        assert moment in fake_llm.prompt, f"key_moment {moment!r} missing from prompt"
    for ref in bundle.references:
        assert ref in fake_llm.prompt, f"reference {ref!r} missing from prompt"
    assert "<event>" in fake_llm.prompt
    assert "<gap>" in fake_llm.prompt
