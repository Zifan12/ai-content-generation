"""Tests for StoryPitcher (src/monitor/story_pitcher.py).

Slice ① (staged director, 2026-07-16): the pitcher emits desire-only
IdeaPitch slates — no beats, no dialogue, no scene staging. The story tests
that used to live here (beat teaching, repitch, credit pricing) moved with
those responsibilities to tests/generation/test_story_architect.py.
"""
import logging

from src.monitor.schemas import (
    CharacterRef,
    ContentMode,
    ContextBundle,
    GapAnalysis,
    IdeaPitch,
    IdeaPitchSlate,
    TrendingEvent,
)
from src.monitor.story_pitcher import StoryPitcher
from src.rag.embedder import TextEmbedder

SAMPLE_EVENT = TrendingEvent(
    headline="Dragon spotted circling Tokyo Tower at dawn",
    subreddit="interestingasfuck",
    url="https://reddit.com/r/interestingasfuck/comments/abc123",
    reaction_sample="Top comment: 'I wish we got to see it actually breathe fire.'",
    trendiness_score=0.92,
    virality_window_hours=18.0,
    raw_source_data={},
    origin="scraped",
)

SAMPLE_GAP = GapAnalysis(
    dominant_emotion="longing",
    audience_want="to see the dragon actually breathe fire",
    evidence_quotes=["I wish we got to see it actually breathe fire."],
    reasoning="The crowd was teased a payoff the footage never delivered.",
)


def _idea(
    logline: str = "The dragon finally breathes fire over Tokyo Tower",
) -> IdeaPitch:
    return IdeaPitch(
        logline=logline,
        mode=ContentMode.wish,
        characters=[CharacterRef(name="the dragon", ip_source="original")],
        desired_moment="the fire breath fans were denied",
        why_it_lands="delivers the payoff the footage cut away from",
        legal_flag=False,
    )


def _slate(loglines: tuple[str, ...] = ("Story one", "A different story two")) -> IdeaPitchSlate:
    return IdeaPitchSlate(ideas=[_idea(logline=line) for line in loglines])


class FakeLLM:
    def __init__(self, result: object) -> None:
        self._result = result

    def parse(self, prompt: str, response_model: type, **kwargs: object) -> object:
        self.prompt = prompt
        self.response_model = response_model
        self.system = kwargs.get("system")
        return self._result


class FakeEmbedder(TextEmbedder):
    def __init__(self, vectors: list[list[float]] | None = None) -> None:
        self._vectors = vectors

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts = texts
        if self._vectors is not None:
            return self._vectors
        basis = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        return [basis[i % 3] for i in range(len(texts))]

    @property
    def dim(self) -> int:
        return 1024

    @property
    def model_name(self) -> str:
        return "fake-embedder"


def _sample_bundle() -> ContextBundle:
    return ContextBundle(
        reaction_sample="I wish we saw the dragon breathe fire",
        summary="Tokyo residents report a dragon at dawn; footage cuts before the fire breath.",
        key_moments=["dragon appears 06:14 JST", "camera cuts before fire breath"],
        references=["https://news.example.com/dragon-tokyo"],
        sources=["tavily", "reddit"],
    )


def test_pitch_returns_idea_slate_and_injects_playbook_gap_event() -> None:
    llm = FakeLLM(_slate())
    embedder = FakeEmbedder()
    # Opt into the playbook (default is now off, 2026-07-10) to test injection.
    pitcher = StoryPitcher(llm=llm, embedder=embedder, use_playbook=True)

    result = pitcher.pitch(SAMPLE_EVENT, SAMPLE_GAP)

    assert len(result.ideas) == 2
    assert llm.response_model is IdeaPitchSlate
    # Both playbook modes injected when use_playbook=True (Option A: full menu).
    assert "wish" in llm.prompt
    assert "satire" in llm.prompt
    assert SAMPLE_EVENT.headline in llm.prompt
    assert SAMPLE_GAP.audience_want in llm.prompt
    assert embedder.texts  # diversity check ran on the loglines


def test_pitch_without_bundle_has_no_context_block() -> None:
    llm = FakeLLM(_slate())
    pitcher = StoryPitcher(llm=llm, embedder=FakeEmbedder())

    pitcher.pitch(SAMPLE_EVENT, SAMPLE_GAP, bundle=None)

    assert "<context>" not in llm.prompt
    assert "<event>" in llm.prompt
    assert "<gap>" in llm.prompt
    assert "<playbook>" in llm.prompt


def test_pitch_with_bundle_injects_context_block() -> None:
    llm = FakeLLM(_slate())
    pitcher = StoryPitcher(llm=llm, embedder=FakeEmbedder())
    bundle = _sample_bundle()

    pitcher.pitch(SAMPLE_EVENT, SAMPLE_GAP, bundle=bundle)

    assert "<context>" in llm.prompt and "</context>" in llm.prompt
    assert bundle.summary in llm.prompt


def test_prompt_is_desire_only_no_beat_instruction() -> None:
    """Slice ① boundary: the pitcher must not be taught to author story
    structure — no beats, no shot sizes, no dialogue instruction. That craft
    moved to the StoryArchitect, and re-teaching it here is exactly the
    defect slice ① removed (obs 2206: the pitcher authored pitch-51's
    beat-free action line because it owned beats without render knowledge).
    """
    llm = FakeLLM(_slate())
    pitcher = StoryPitcher(llm=llm, embedder=FakeEmbedder())

    pitcher.pitch(SAMPLE_EVENT, SAMPLE_GAP)

    assert "desired_moment" in llm.system
    assert "no caption, no voiceover, no on-screen text" in llm.system
    assert "StoryBeat" not in llm.system
    assert "shot_size" not in llm.system
    assert "dialogue_line" not in llm.system
    assert "scene_setting" not in llm.system


def test_low_diversity_slate_warns(caplog) -> None:
    llm = FakeLLM(_slate(("Story one", "A different story two")))
    embedder = FakeEmbedder(vectors=[[1.0, 0.0, 0.0], [0.99, 0.01, 0.0]])
    pitcher = StoryPitcher(llm=llm, embedder=embedder)

    with caplog.at_level(logging.WARNING):
        pitcher.pitch(SAMPLE_EVENT, SAMPLE_GAP)

    assert any("low diversity" in record.message for record in caplog.records)


def test_distinct_slate_does_not_warn(caplog) -> None:
    llm = FakeLLM(_slate(("Story one", "A different story two")))
    embedder = FakeEmbedder(vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    pitcher = StoryPitcher(llm=llm, embedder=embedder)

    with caplog.at_level(logging.WARNING):
        pitcher.pitch(SAMPLE_EVENT, SAMPLE_GAP)

    assert not any("low diversity" in record.message for record in caplog.records)
