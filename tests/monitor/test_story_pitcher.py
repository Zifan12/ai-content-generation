"""Tests for StoryPitcher (src/monitor/story_pitcher.py, Stage B)."""
import logging

from src.monitor.schemas import (
    BeatRole,
    CaptionPolicy,
    CharacterRef,
    ContentMode,
    ContextBundle,
    GapAnalysis,
    ShotSize,
    StoryBeat,
    StoryPitch,
    StoryPitchSlate,
    TrendingEvent,
)
from src.monitor.story_pitcher import StoryPitcher, estimate_pitch_credits
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
    virality_window_hours=18.0,
    reasoning="The crowd was teased a payoff the footage never delivered.",
)


def _beat(
    role: BeatRole = BeatRole.hook,
    shot_size: ShotSize = ShotSize.wide,
    hero: bool = False,
) -> StoryBeat:
    return StoryBeat(
        role=role,
        visual_line="x",
        narration_line=None,
        shot_size=shot_size,
        characters_in_frame=["Eve"],
        hero_moment=hero,
    )


def _default_beats() -> list[StoryBeat]:
    return [
        _beat(BeatRole.hook, ShotSize.wide),
        _beat(BeatRole.turn, ShotSize.medium),
        _beat(BeatRole.payoff, ShotSize.close_up, hero=True),
    ]


def _pitch(
    logline: str = "The dragon finally breathes fire over Tokyo Tower",
    beats: list[StoryBeat] | None = None,
) -> StoryPitch:
    return StoryPitch(
        logline=logline,
        mode=ContentMode.wish,
        characters=[CharacterRef(name="the dragon", ip_source="original")],
        desired_moment="the fire breath fans were denied",
        beats=beats or _default_beats(),
        caption_policy=CaptionPolicy.hook_only,
        hook_line="the ending they owed us",
        why_it_lands="delivers the payoff the footage cut away from",
        legal_flag=False,
    )


def _slate(loglines: tuple[str, ...] = ("Story one", "A different story two")) -> StoryPitchSlate:
    return StoryPitchSlate(pitches=[_pitch(logline=line) for line in loglines])


class FakeLLM:
    def __init__(self, result: object) -> None:
        self._result = result

    def parse(self, prompt: str, response_model: type, **kwargs: object) -> object:
        self.prompt = prompt
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


def test_pitch_returns_slate_and_injects_playbook_gap_event() -> None:
    llm = FakeLLM(_slate())
    embedder = FakeEmbedder()
    pitcher = StoryPitcher(llm=llm, embedder=embedder)

    result = pitcher.pitch(SAMPLE_EVENT, SAMPLE_GAP)

    assert len(result.pitches) == 2
    # Both playbook modes injected (Option A: full menu in every prompt).
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


def test_repitch_returns_single_pitch_and_carries_failure_notes() -> None:
    repaired = _pitch(logline="Repaired: the dragon breathes fire, earned by a clear turn")
    llm = FakeLLM(repaired)
    pitcher = StoryPitcher(llm=llm, embedder=FakeEmbedder())
    failed = _pitch(logline="Flat: the dragon just stands in fire the whole time")

    result = pitcher.repitch(
        SAMPLE_EVENT, SAMPLE_GAP, failed, "no visible turn; payoff unearned"
    )

    assert isinstance(result, StoryPitch)
    assert result.logline.startswith("Repaired")
    assert "no visible turn" in llm.prompt
    assert failed.logline in llm.prompt
    assert "<failed_pitch>" in llm.prompt and "<failure_notes>" in llm.prompt


def test_estimate_pitch_credits_scales_with_beats() -> None:
    assert estimate_pitch_credits(_pitch()) == 28.5  # 3 beats * (2 + 7.5)
    five = _pitch(
        beats=[
            _beat(BeatRole.hook, ShotSize.wide),
            _beat(BeatRole.establish, ShotSize.establishing),
            _beat(BeatRole.turn, ShotSize.over_shoulder),
            _beat(BeatRole.reveal, ShotSize.close_up),
            _beat(BeatRole.payoff, ShotSize.extreme_close_up, hero=True),
        ]
    )
    assert estimate_pitch_credits(five) == 47.5  # 5 beats * 9.5


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
