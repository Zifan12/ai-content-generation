"""Tests for ContentWriter v3 (plan 2026-07-04 Task 4 — two-call multi-shot flow).

FakeLLM answers by response_model type: ShotPlanDraft requests get the queued
draft; DialectConversion requests get one "CONVERTED[i]" prompt per shot line in
the envelope (counted from the "motion_intent:" markers), unless a broken
conversion is forced. No network, no credits.
"""

import pytest

from src.generation.content_writer import (
    DIALECT_SYSTEM_PROMPT,
    PLAN_SYSTEM_PROMPT,
    WRITER_MAX_TOKENS,
    ContentWriter,
    DialectConversion,
)
from src.generation.render_adapters.rules import RenderRules
from src.monitor.schemas import (
    BeatRole,
    CaptionPolicy,
    CharacterRef,
    ContentMode,
    ShotSize,
    StoryBeat,
    StoryPitch,
)
from src.schemas.generation import (
    MotionTag,
    MultiShotPackage,
    ShotDraft,
    ShotPlanDraft,
)

ANCHOR_TEXT = "ANCHOR_SENTINEL Eve short tousled dark-brown hair pure-white bodysuit"
STYLE_TEXT = "STYLE_SENTINEL cel-shaded TV anime thick line art"

_SIZES = [
    ShotSize.establishing,
    ShotSize.medium,
    ShotSize.close_up,
    ShotSize.wide,
    ShotSize.over_shoulder,
    ShotSize.extreme_close_up,
]


def _pitch(n_beats: int = 3, narrations: list[str | None] | None = None) -> StoryPitch:
    if narrations is None:
        narrations = ["Narration line."] * n_beats
    beats = [
        StoryBeat(
            role=BeatRole.hook if i == 0 else BeatRole.build,
            visual_line=f"Beat {i}: the swordswoman advances through the rain.",
            narration_line=narrations[i],
            shot_size=_SIZES[i % len(_SIZES)],
            characters_in_frame=["Eve"],
            hero_moment=False,
        )
        for i in range(n_beats)
    ]
    return StoryPitch(
        logline="Eve gets the ending the fans wanted.",
        mode=ContentMode.wish,
        characters=[CharacterRef(name="Eve", ip_source="Stellar Blade")],
        desired_moment="The confrontation the trailer denied.",
        beats=beats,
        caption_policy=CaptionPolicy.hook_only,
        hook_line="the ending they cut",
        why_it_lands="Fans are begging for exactly this beat.",
        legal_flag=False,
    )


def _draft_shots(
    n: int,
    tag: MotionTag = MotionTag.character_consistency,
    narration: str | None = "Polished narration.",
) -> list[ShotDraft]:
    return [
        ShotDraft(
            beat_role=BeatRole.build,  # deliberately wrong: writer must copy pitch's
            motion_tag=tag,
            still_prompt=f"Shot {i} still: the swordswoman mid-stride, low angle.",
            motion_intent=f"Shot {i}: slow push-in, she turns on the final second.",
            duration_seconds=4,
            narration_line=narration,
            characters_in_frame=["WRONG_ECHO"],  # writer must copy pitch's
        )
        for i in range(n)
    ]


def _plan(shots: list[ShotDraft]) -> ShotPlanDraft:
    return ShotPlanDraft(
        shots=shots,
        style_anchor=STYLE_TEXT,
        anchors_block=ANCHOR_TEXT,
        hook_text="DRAFT HOOK — must lose to pitch.hook_line",
        caption="they finally rendered it",
        hashtags=["stellarblade", "fyp"],
        music_brief="slow strings, single piano hit",
        rationale="test rationale",
    )


class FakeLLM:
    def __init__(self, plan: ShotPlanDraft, conversion_prompts: list[str] | None = None):
        self._plan = plan
        self._forced_conversion = conversion_prompts
        self.calls: list[dict] = []

    def parse(self, prompt, response_model, system=None, max_tokens=1024):
        self.calls.append(
            {
                "prompt": prompt,
                "response_model": response_model,
                "system": system,
                "max_tokens": max_tokens,
            }
        )
        if response_model is ShotPlanDraft:
            return self._plan
        if response_model is DialectConversion:
            if self._forced_conversion is not None:
                return DialectConversion(motion_prompts=self._forced_conversion)
            n = prompt.count("motion_intent:")
            return DialectConversion(
                motion_prompts=[f"CONVERTED[{i}]. Audio: rain on pavement." for i in range(n)]
            )
        raise AssertionError(f"unexpected response_model {response_model}")


@pytest.fixture(scope="module")
def rules():
    return RenderRules()


def _write(pitch, fake, rules, refs=None, pitch_id=7):
    return ContentWriter(llm=fake).write(
        pitch,
        rules=rules,
        reference_image_paths=refs if refs is not None else ["refs/eve_1.jpg"],
        pitch_id=pitch_id,
    )


# --- cardinality passthrough ---------------------------------------------------


def test_three_beats_three_shots(rules):
    package = _write(_pitch(3), FakeLLM(_plan(_draft_shots(3))), rules)
    assert isinstance(package, MultiShotPackage)
    assert len(package.shots) == 3


def test_six_beats_six_shots(rules):
    package = _write(_pitch(6), FakeLLM(_plan(_draft_shots(6))), rules)
    assert len(package.shots) == 6


def test_plan_beat_count_mismatch_raises(rules):
    with pytest.raises(ValueError, match="one shot per beat"):
        _write(_pitch(4), FakeLLM(_plan(_draft_shots(3))), rules)


# --- code beats LLM at every seam ------------------------------------------------


def test_beat_role_and_cast_copied_from_pitch_not_draft(rules):
    package = _write(_pitch(3), FakeLLM(_plan(_draft_shots(3))), rules)
    assert package.shots[0].beat_role == BeatRole.hook  # draft echoed 'build'
    assert all(shot.characters_in_frame == ["Eve"] for shot in package.shots)


def test_silent_beat_stays_silent_even_if_draft_invents_narration(rules):
    pitch = _pitch(3, narrations=["A line.", None, "Another line."])
    package = _write(pitch, FakeLLM(_plan(_draft_shots(3))), rules)
    assert package.shots[0].narration_line == "Polished narration."
    assert package.shots[1].narration_line is None  # draft supplied text; pitch wins
    assert package.shots[2].narration_line == "Polished narration."


def test_model_stamped_from_router_table(rules):
    package = _write(_pitch(3), FakeLLM(_plan(_draft_shots(3))), rules)
    assert all(
        shot.model_cli_id == rules.route(shot.motion_tag.value)[0]
        for shot in package.shots
    )
    assert package.shots[0].model_cli_id == "kling3_0"


def test_hook_text_is_pitch_hook_line_not_draft(rules):
    package = _write(_pitch(3), FakeLLM(_plan(_draft_shots(3))), rules)
    assert package.hook_text == "the ending they cut"


def test_provenance_code_set(rules):
    package = _write(
        _pitch(3), FakeLLM(_plan(_draft_shots(3))), rules, refs=["a.jpg", "b.jpg"]
    )
    assert package.pitch_id == 7
    assert package.reference_image_paths == ["a.jpg", "b.jpg"]
    assert package.consistency_groups == [[0, 1, 2]]  # 3x4s kling same-cast


# --- anchors/style exclusion (spec §7 Stage-2 criterion 6) ------------------------


def test_no_shot_prompt_contains_anchor_or_style_text(rules):
    package = _write(_pitch(3), FakeLLM(_plan(_draft_shots(3))), rules)
    for shot in package.shots:
        assert ANCHOR_TEXT not in shot.still_prompt
        assert ANCHOR_TEXT not in shot.motion_prompt
        assert STYLE_TEXT not in shot.still_prompt
        assert STYLE_TEXT not in shot.motion_prompt
    assert package.anchors_block == ANCHOR_TEXT
    assert package.style_anchor == STYLE_TEXT


# --- call mechanics ---------------------------------------------------------------


def test_two_calls_one_model_and_prompt_contents(rules):
    fake = FakeLLM(_plan(_draft_shots(3)))
    _write(_pitch(3), fake, rules)
    assert len(fake.calls) == 2  # one plan + one dialect (all shots -> kling)
    plan_call, dialect_call = fake.calls
    assert plan_call["system"] == PLAN_SYSTEM_PROMPT
    assert plan_call["max_tokens"] == WRITER_MAX_TOKENS
    assert "Still dialect:" in plan_call["prompt"]
    assert "Motion craft:" in plan_call["prompt"]
    assert "the ending they cut" in plan_call["prompt"]  # pitch JSON present
    assert dialect_call["system"] == DIALECT_SYSTEM_PROMPT
    assert dialect_call["max_tokens"] == WRITER_MAX_TOKENS
    # the kling dialect block travels into the dialect envelope
    assert rules.model("kling3_0")["dialect"]["multi_shot_grammar"] in dialect_call["prompt"]
    assert "group [0, 1, 2]" in dialect_call["prompt"]


def test_one_dialect_call_per_distinct_model(rules):
    shots = _draft_shots(3)
    shots[1] = ShotDraft(
        beat_role=BeatRole.build,
        motion_tag=MotionTag.fluid_motion,
        still_prompt="Wave still.",
        motion_intent="Water arcs over the wall, edges holding.",
        duration_seconds=4,
        narration_line="x",
        characters_in_frame=["WRONG_ECHO"],
    )
    fake = FakeLLM(_plan(shots))
    package = _write(_pitch(3), fake, rules)
    assert len(fake.calls) == 3  # plan + kling batch + veo batch
    assert package.shots[1].model_cli_id == "veo3_1"  # hailuo pulled (BUG-011)
    assert package.consistency_groups == [[0], [1], [2]]  # breakout splits the run


def test_dialect_count_mismatch_raises(rules):
    fake = FakeLLM(_plan(_draft_shots(3)), conversion_prompts=["only one"])
    with pytest.raises(ValueError, match="returned 1 prompts for 3 shots"):
        _write(_pitch(3), fake, rules)


def test_motion_prompts_assigned_in_shot_order(rules):
    package = _write(_pitch(3), FakeLLM(_plan(_draft_shots(3))), rules)
    assert [shot.motion_prompt for shot in package.shots] == [
        "CONVERTED[0]. Audio: rain on pavement.",
        "CONVERTED[1]. Audio: rain on pavement.",
        "CONVERTED[2]. Audio: rain on pavement.",
    ]
