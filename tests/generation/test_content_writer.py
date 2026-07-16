"""Tests for ContentWriter (motion-native scene lane, director merge 2026-07-15).

FakeLLM answers the ONE director call with a queued DirectorDraft. Since the
2026-07-15 merge there is only one response model to answer — scene_line is a
field of each drafted shot, not a second call's separate output — so a test that
wants specific shipped prose queues shots carrying it. No network, no credits.
"""

import pytest

from src.generation.content_writer import (
    DIRECTOR_SYSTEM_PROMPT,
    WRITER_MAX_TOKENS,
    ContentWriter,
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
    DirectorDraft,
    DirectorShotDraft,
    MotionTag,
    MultiShotPackage,
)

_SIZES = [
    ShotSize.establishing,
    ShotSize.medium,
    ShotSize.close_up,
    ShotSize.wide,
    ShotSize.over_shoulder,
    ShotSize.extreme_close_up,
]


def _pitch(
    n_beats: int = 3,
    narrations: list[str | None] | None = None,
    dialogue: dict[int, tuple[str, str]] | None = None,
) -> StoryPitch:
    if narrations is None:
        narrations = [None] * n_beats
    dialogue = dialogue or {}
    beats = [
        StoryBeat(
            role=BeatRole.hook if i == 0 else BeatRole.build,
            visual_line=f"Beat {i}: the swordswoman advances through the rain.",
            narration_line=narrations[i],
            dialogue_line=dialogue.get(i, (None, None))[0],
            speaker=dialogue.get(i, (None, None))[1],
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
        scene_setting="a rain-soaked academy courtyard, dusk",
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
    lines: list[str] | None = None,
) -> list[DirectorShotDraft]:
    """n drafted shots whose every code-copied field deliberately CONTRADICTS the
    pitch, so a test that passes proves code won rather than that the echo agreed.
    `lines` forces the shipped prose when a test cares about it."""
    return [
        DirectorShotDraft(
            beat_role=BeatRole.build,  # deliberately wrong: writer must copy pitch's
            motion_tag=tag,
            scene_line=(
                lines[i] if lines is not None
                else f"CONVERTED[{i}]. Audio: rain on pavement."
            ),
            duration_seconds=4,
            narration_line=narration,
            characters_in_frame=["WRONG_ECHO"],  # writer must copy pitch's
        )
        for i in range(n)
    ]


def _plan(shots: list[DirectorShotDraft]) -> DirectorDraft:
    return DirectorDraft(
        shots=shots,
        hook_text="DRAFT HOOK — must lose to pitch.hook_line",
        caption="they finally rendered it",
        hashtags=["stellarblade", "fyp"],
        music_brief="slow strings, single piano hit",
        rationale="test rationale",
    )


class FakeLLM:
    def __init__(
        self,
        draft: DirectorDraft,
        draft_queue: list[DirectorDraft] | None = None,
    ):
        self._draft = draft
        self._queue = draft_queue  # one entry per director call (budget retries)
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
        if response_model is DirectorDraft:
            if self._queue:
                return self._queue.pop(0)
            return self._draft
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


def test_five_beats_five_shots(rules):
    package = _write(_pitch(5), FakeLLM(_plan(_draft_shots(5))), rules)
    assert len(package.shots) == 5


def test_director_beat_count_mismatch_raises(rules):
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


def test_model_stamped_from_scene_lane_config(rules):
    package = _write(_pitch(3), FakeLLM(_plan(_draft_shots(3))), rules)
    assert all(
        shot.model_cli_id == rules.scene_model() for shot in package.shots
    )
    assert package.shots[0].model_cli_id == "seedance_2_0"


def test_hook_text_is_always_none(rules):
    package = _write(_pitch(3), FakeLLM(_plan(_draft_shots(3))), rules)
    assert package.hook_text is None


def test_dialogue_and_speaker_copied_from_pitch_not_draft(rules):
    pitch = _pitch(3, dialogue={1: ("Wait, don't!", "Eve")})
    package = _write(pitch, FakeLLM(_plan(_draft_shots(3))), rules)
    assert package.shots[0].dialogue_line is None
    assert package.shots[0].speaker is None
    assert package.shots[1].dialogue_line == "Wait, don't!"
    assert package.shots[1].speaker == "Eve"


def test_director_envelope_carries_dialogue(rules):
    """The director reads the pitch itself, so the dialogue pair rides along in the
    beat JSON. The deleted scene call had to be hand-fed this: it never saw the
    pitch, only a paraphrase, so code copied dialogue into its envelope by hand."""
    pitch = _pitch(3, dialogue={1: ("Wait, don't!", "Eve")})
    fake = FakeLLM(_plan(_draft_shots(3)))
    _write(pitch, fake, rules)
    director_call = fake.calls[0]
    assert '"dialogue_line": "Wait, don\'t!"' in director_call["prompt"]
    assert '"speaker": "Eve"' in director_call["prompt"]


def test_scene_line_over_90_words_raises(rules):
    # Hard cap recalibrated 40-soft/60-hard -> 65-soft/90-hard (2026-07-11,
    # video-researcher evidence). 91 words is a genuine runaway.
    long_line = "word " * 91
    fake = FakeLLM(
        _plan(
            _draft_shots(
                3,
                lines=[long_line, "CONVERTED[1]. Audio: rain.", "CONVERTED[2]. Audio: rain."],
            )
        )
    )
    with pytest.raises(ValueError, match="hard cap"):
        _write(_pitch(3), fake, rules)


def test_scene_line_at_65_words_is_accepted(rules):
    # The realistic case the old 60-cap false-failed: a line packing camera +
    # action + space + dialogue + audio lands ~55-65 words and must NOT be rejected.
    line_65 = "word " * 65 + "Audio: rain."
    fake = FakeLLM(
        _plan(
            _draft_shots(
                3,
                lines=[line_65, "CONVERTED[1]. Audio: rain.", "CONVERTED[2]. Audio: rain."],
            )
        )
    )
    package = _write(_pitch(3), fake, rules)  # no raise
    assert package.shots[0].scene_line.startswith("word")


# --- composed-prompt budget: one bounded repair (pitch-43 regression) --------------

# ≤90 words each (passes the per-line cap) but char-fat: the exact failure shape
# that blew the adapter's 3000-char guard on pitch-43 — every line legal, sum over.
_FAT_LINES = ["wordwordword " * 85] * 3
_SLIM_LINES = [f"SLIM[{i}]. Audio: rain." for i in range(3)]


def test_scene_budget_blown_retries_once_with_feedback(rules):
    fake = FakeLLM(
        _plan(_draft_shots(3)),
        draft_queue=[
            _plan(_draft_shots(3, lines=list(_FAT_LINES))),
            _plan(_draft_shots(3, lines=list(_SLIM_LINES))),
        ],
    )
    package = _write(_pitch(3), fake, rules)
    assert len(fake.calls) == 2  # first director call + ONE repair re-call
    retry_call = fake.calls[1]
    assert retry_call["prompt"].startswith("<story>")  # same data, plus feedback
    assert "REWRITE:" in retry_call["prompt"]
    assert "characters_in_frame" in retry_call["prompt"]
    assert [shot.scene_line for shot in package.shots] == _SLIM_LINES


def test_scene_budget_still_blown_after_repair_raises(rules):
    fat = _plan(_draft_shots(3, lines=list(_FAT_LINES)))
    fake = FakeLLM(fat, draft_queue=[fat, _plan(_draft_shots(3, lines=list(_FAT_LINES)))])
    with pytest.raises(ValueError, match="composed-prompt budget"):
        _write(_pitch(3), fake, rules)
    assert len(fake.calls) == 2  # 2 director attempts, no third


def test_scene_budget_fit_first_try_makes_no_retry(rules):
    fake = FakeLLM(_plan(_draft_shots(3)))
    _write(_pitch(3), fake, rules)
    assert len(fake.calls) == 1  # happy path is ONE call since the director merge


def test_provenance_code_set(rules):
    package = _write(
        _pitch(3), FakeLLM(_plan(_draft_shots(3))), rules, refs=["a.jpg", "b.jpg"]
    )
    assert package.pitch_id == 7
    assert package.reference_image_paths == ["a.jpg", "b.jpg"]


def test_location_grounding_stamped_through(rules):
    package = ContentWriter(llm=FakeLLM(_plan(_draft_shots(3)))).write(
        _pitch(3),
        rules=rules,
        reference_image_paths=["refs/eve/front.png"],
        pitch_id=7,
        world_anchor="A grand ice-tower chamber, pale marble floor.",
        location_reference_paths=["refs/_location/elfie_bedroom/room.jpg"],
    )
    assert package.world_anchor == "A grand ice-tower chamber, pale marble floor."
    assert package.location_reference_paths == ["refs/_location/elfie_bedroom/room.jpg"]


def test_location_grounding_defaults_empty_when_absent(rules):
    # An ungrounded write (the current smoke default) stamps empty carriers.
    package = _write(_pitch(3), FakeLLM(_plan(_draft_shots(3))), rules)
    assert package.world_anchor == ""
    assert package.location_reference_paths == []


def test_writer_calls_receive_the_world_anchor(rules):
    """The writer invented rooms because it had never seen one: the envelope never
    carried world_anchor (it was only subtracted from the char budget). Measured
    2026-07-14 pitch 47 — the scene line said "a dim stone chamber lit by a single
    torch" while world_anchor in the SAME prompt said "ornate white marble bedroom,
    tall windows"."""
    seen = []

    class CapturingLLM:
        def __init__(self, delegate):
            self._delegate = delegate

        def parse(self, prompt, response_model, system=None, max_tokens=1024):
            seen.append(prompt)
            return self._delegate.parse(prompt, response_model, system, max_tokens)

    ContentWriter(llm=CapturingLLM(FakeLLM(_plan(_draft_shots(3))))).write(
        _pitch(3),
        rules=rules,
        reference_image_paths=["refs/eve/front.png"],
        world_anchor="A grand ice-tower chamber, pale marble floor.",
    )
    # >= 1, not == 1: the director call has a budget-repair retry loop that
    # re-calls on an over-budget candidate (observed live 2026-07-14: "scene body
    # 1882 chars over its 1812 budget (attempt 1/2) — retrying"). Pinning an exact
    # count would make this test fail on a legitimate repair.
    assert len(seen) >= 1  # the director call, plus any budget repair
    assert all("A grand ice-tower chamber" in p for p in seen)


# --- call mechanics ---------------------------------------------------------------


def test_one_call_and_prompt_contents(rules):
    fake = FakeLLM(_plan(_draft_shots(3)))
    _write(_pitch(3), fake, rules)
    assert len(fake.calls) == 1  # ONE director call, always (PRD D1)
    director_call = fake.calls[0]
    assert director_call["system"] == DIRECTOR_SYSTEM_PROMPT
    assert director_call["max_tokens"] == WRITER_MAX_TOKENS
    assert "Motion craft:" in director_call["prompt"]
    assert "Still dialect:" not in director_call["prompt"]  # scene lane writes no stills
    assert "the ending they cut" in director_call["prompt"]  # pitch JSON present


def test_pitch_travels_inside_the_injection_guard(rules):
    """The pitch is untrusted data (a beat's prose could read as an instruction), so
    it rides inside <story> tags the system prompt tells the model to treat as
    material only. Instructions to the director — the craft rules, the location —
    must stay OUTSIDE the tags, or the guard would disarm them too."""
    fake = FakeLLM(_plan(_draft_shots(3)))
    ContentWriter(llm=fake).write(
        _pitch(3),
        rules=rules,
        reference_image_paths=["refs/eve/front.png"],
        world_anchor="A grand ice-tower chamber, pale marble floor.",
    )
    prompt = fake.calls[0]["prompt"]
    assert prompt.startswith("<story>")
    body, _, after_guard = prompt.partition("</story>")
    assert "the swordswoman advances through the rain" in body  # beats: inside
    assert "Motion craft:" in after_guard  # instructions to obey: outside
    assert "A grand ice-tower chamber" in after_guard


def test_mixed_motion_tags_still_one_call(rules):
    shots = _draft_shots(3)
    shots[1] = DirectorShotDraft(
        beat_role=BeatRole.build,
        motion_tag=MotionTag.fluid_motion,
        scene_line="Water arcs over the wall, edges holding. Audio: the hiss of spray.",
        duration_seconds=4,
        narration_line="x",
        characters_in_frame=["WRONG_ECHO"],
    )
    fake = FakeLLM(_plan(shots))
    package = _write(_pitch(3), fake, rules)
    assert len(fake.calls) == 1  # tags are metadata — no per-model batching (D3)
    assert {shot.model_cli_id for shot in package.shots} == {rules.scene_model()}


# A line-count mismatch used to be its own failure mode (the scene call could
# return 1 line for 3 shots) and had its own test. Since the director merge,
# scene_line is a FIELD of each drafted shot, so structured output makes one line
# per shot structurally guaranteed — the only count that can still be wrong is
# shots-vs-beats, covered by test_director_beat_count_mismatch_raises.


def test_scene_lines_assigned_in_shot_order(rules):
    package = _write(_pitch(3), FakeLLM(_plan(_draft_shots(3))), rules)
    assert [shot.scene_line for shot in package.shots] == [
        "CONVERTED[0]. Audio: rain on pavement.",
        "CONVERTED[1]. Audio: rain on pavement.",
        "CONVERTED[2]. Audio: rain on pavement.",
    ]
