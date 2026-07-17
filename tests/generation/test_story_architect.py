"""Tests for StoryArchitect (src/generation/story_architect.py, stage D1).

Mirrors tests/monitor/test_story_pitcher.py's FakeLLM idiom. The beat-craft
prompt tests and the repair/credit tests moved HERE with those
responsibilities (slice ①, 2026-07-16).

The composition tests are the slice's load-bearing guarantees:
- idea fields are CODE-COPIED into the StoryScript, never taken from an LLM
  echo (the trust-code-over-LLM doctrine);
- the beats the LLM authored reach the script IDENTICALLY (no paraphrase hop
  can be silently reintroduced between the beat author and the writer — the
  2026-07-15 PRD's structural guarantee, re-pointed at the new boundary).
"""

from src.monitor.schemas import (
    BeatRole,
    CharacterRef,
    ContentMode,
    ContextBundle,
    GapAnalysis,
    IdeaPitch,
    ScriptDraft,
    ShotSize,
    StoryBeat,
    StoryScript,
    TrendingEvent,
)
from src.generation.story_architect import (
    StoryArchitect,
    estimate_script_credits,
)

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

SAMPLE_IDEA = IdeaPitch(
    logline="The dragon finally breathes fire over Tokyo Tower",
    mode=ContentMode.wish,
    characters=[CharacterRef(name="the dragon", ip_source="original")],
    desired_moment="the fire breath fans were denied",
    why_it_lands="delivers the payoff the footage cut away from",
    legal_flag=False,
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
        characters_in_frame=["the dragon"],
        hero_moment=hero,
    )


def _default_beats() -> list[StoryBeat]:
    return [
        _beat(BeatRole.hook, ShotSize.wide),
        _beat(BeatRole.turn, ShotSize.medium),
        _beat(BeatRole.payoff, ShotSize.close_up, hero=True),
    ]


def _draft(beats: list[StoryBeat] | None = None) -> ScriptDraft:
    return ScriptDraft(
        scene_setting="the tower's observation deck, dawn light",
        beats=beats or _default_beats(),
    )


def _script(beats: list[StoryBeat] | None = None) -> StoryScript:
    return StoryScript(
        logline=SAMPLE_IDEA.logline,
        mode=SAMPLE_IDEA.mode,
        characters=SAMPLE_IDEA.characters,
        desired_moment=SAMPLE_IDEA.desired_moment,
        scene_setting="the tower's observation deck, dawn light",
        beats=beats or _default_beats(),
        why_it_lands=SAMPLE_IDEA.why_it_lands,
        legal_flag=SAMPLE_IDEA.legal_flag,
    )


class FakeLLM:
    def __init__(self, result: object) -> None:
        self._result = result

    def parse(self, prompt: str, response_model: type, **kwargs: object) -> object:
        self.prompt = prompt
        self.response_model = response_model
        self.system = kwargs.get("system")
        return self._result


def _sample_bundle() -> ContextBundle:
    return ContextBundle(
        reaction_sample="I wish we saw the dragon breathe fire",
        summary="Tokyo residents report a dragon at dawn; footage cuts before the fire breath.",
        key_moments=["dragon appears 06:14 JST", "camera cuts before fire breath"],
        references=["https://news.example.com/dragon-tokyo"],
        sources=["tavily", "reddit"],
    )


def test_develop_composes_script_with_idea_fields_code_copied() -> None:
    """The LLM returns staging only; every idea field on the script must be
    the idea's own value, copied by code — the model has no channel to
    override them because ScriptDraft doesn't carry them at all.
    """
    llm = FakeLLM(_draft())
    architect = StoryArchitect(llm=llm)

    script = architect.develop(SAMPLE_IDEA, SAMPLE_EVENT, SAMPLE_GAP)

    assert llm.response_model is ScriptDraft
    assert script.logline == SAMPLE_IDEA.logline
    assert script.mode is SAMPLE_IDEA.mode
    assert script.characters == SAMPLE_IDEA.characters
    assert script.desired_moment == SAMPLE_IDEA.desired_moment
    assert script.why_it_lands == SAMPLE_IDEA.why_it_lands
    assert script.legal_flag is SAMPLE_IDEA.legal_flag
    assert script.scene_setting == "the tower's observation deck, dawn light"


def test_develop_passes_beats_through_identically() -> None:
    """No paraphrase hop between the beat author and the composed script:
    the ScriptDraft's beat objects ARE the StoryScript's beat objects.
    Reintroduce a rewrite stage and this fails (the 07-15 PRD guarantee,
    re-pointed at the new stage boundary).
    """
    beats = _default_beats()
    architect = StoryArchitect(llm=FakeLLM(_draft(beats=beats)))

    script = architect.develop(SAMPLE_IDEA, SAMPLE_EVENT, SAMPLE_GAP)

    assert all(got is authored for got, authored in zip(script.beats, beats))
    assert len(script.beats) == len(beats)


def test_develop_injects_idea_event_gap_blocks() -> None:
    llm = FakeLLM(_draft())
    architect = StoryArchitect(llm=llm)

    architect.develop(SAMPLE_IDEA, SAMPLE_EVENT, SAMPLE_GAP)

    assert "<idea>" in llm.prompt
    assert SAMPLE_IDEA.desired_moment in llm.prompt
    assert SAMPLE_EVENT.headline in llm.prompt
    assert SAMPLE_GAP.audience_want in llm.prompt


def test_develop_without_bundle_has_no_context_block() -> None:
    llm = FakeLLM(_draft())
    architect = StoryArchitect(llm=llm)

    architect.develop(SAMPLE_IDEA, SAMPLE_EVENT, SAMPLE_GAP, bundle=None)

    assert "<context>" not in llm.prompt


def test_develop_with_bundle_and_voices_injects_blocks() -> None:
    llm = FakeLLM(_draft())
    architect = StoryArchitect(llm=llm)
    bundle = _sample_bundle()

    architect.develop(
        SAMPLE_IDEA,
        SAMPLE_EVENT,
        SAMPLE_GAP,
        bundle=bundle,
        cast_voices="<cast_voices>\n### the-dragon\ngrowls\n</cast_voices>",
    )

    assert "<context>" in llm.prompt
    assert bundle.summary in llm.prompt
    assert "<cast_voices>" in llm.prompt


def test_repair_returns_composed_script_and_carries_failure_notes() -> None:
    repaired_beats = _default_beats()
    llm = FakeLLM(_draft(beats=repaired_beats))
    architect = StoryArchitect(llm=llm)
    failed = _script()

    result = architect.repair(
        SAMPLE_IDEA, SAMPLE_EVENT, SAMPLE_GAP, failed,
        "no visible turn; payoff unearned",
    )

    assert isinstance(result, StoryScript)
    assert result.logline == SAMPLE_IDEA.logline  # idea fields still code-copied
    assert all(got is authored for got, authored in zip(result.beats, repaired_beats))
    assert "no visible turn" in llm.prompt
    assert failed.logline in llm.prompt
    assert "<failed_script>" in llm.prompt and "<failure_notes>" in llm.prompt


def test_prompt_teaches_beats_scene_and_no_narration() -> None:
    llm = FakeLLM(_draft())
    architect = StoryArchitect(llm=llm)

    architect.develop(SAMPLE_IDEA, SAMPLE_EVENT, SAMPLE_GAP)

    assert "scene_setting" in llm.system
    assert "3-5 ordered StoryBeats" in llm.system
    assert "no caption, no voiceover, no on-screen text" in llm.system


def test_prompt_teaches_profiled_characters_must_speak() -> None:
    """Q3-B rule 8 moved from the pitcher's prompt to the architect's with
    dialogue authorship (slice ①)."""
    llm = FakeLLM(_draft())
    architect = StoryArchitect(llm=llm)

    architect.develop(SAMPLE_IDEA, SAMPLE_EVENT, SAMPLE_GAP)

    assert "dialogue_line" in llm.system
    assert "<cast_voices>" in llm.system
    assert "stays silent" in llm.system


def test_prompt_keeps_one_continuous_move_rule_uncompressed() -> None:
    """PRD D4: the rule travels with its defining example. The bare phrase
    'ONE subject action' stripped of its example is what killed pitch-47's
    lift; relocation must not re-compress it.
    """
    llm = FakeLLM(_draft())
    architect = StoryArchitect(llm=llm)

    architect.develop(SAMPLE_IDEA, SAMPLE_EVENT, SAMPLE_GAP)

    assert "ONE FLOWING MOTION" in llm.system
    assert "lifts the egg" in llm.system  # the far-domain defining example


def test_estimate_script_credits_scales_with_beats() -> None:
    assert estimate_script_credits(_script()) == 40.5  # 3 beats * 3s * 4.5 cr/s
    five = _script(
        beats=[
            _beat(BeatRole.hook, ShotSize.wide),
            _beat(BeatRole.establish, ShotSize.establishing),
            _beat(BeatRole.turn, ShotSize.over_shoulder),
            _beat(BeatRole.reveal, ShotSize.close_up),
            _beat(BeatRole.payoff, ShotSize.extreme_close_up, hero=True),
        ]
    )
    assert estimate_script_credits(five) == 67.5  # 5 beats * 3s * 4.5 cr/s
