"""Tests for the v3 multi-shot generation schemas (plan 2026-07-04 Task 1).

Covers the assertion contracts from the plan (bounds updated 2026-07-06 for the
motion-native scene lane — envelope 10-25s, per-shot estimate 2-8s):
  - shot cardinality bounds (2 rejected, 6 and 7 rejected, 3 and 5 accepted)
  - per-shot duration-estimate bounds (1s and 9s rejected)
  - total-duration envelope (26s rejected; 9s rejected — constructible now that
    the per-shot floor is 2s; 10s, 12s and 25s accepted)
  - MotionTag values == config/render_rules.yaml routing keys (parity, D5)
  - extra="forbid" on every v3 class (LLM hallucinated-field guard)

Legacy single-shot tests are kept at the bottom until Tasks 4/5 delete the legacy
classes (see the legacy note in src/schemas/generation.py).
"""

import pytest
from pydantic import ValidationError

from src.generation.render_adapters.rules import RenderRules
from src.monitor.schemas import BeatRole
from src.schemas.generation import (
    MotionTag,
    MultiShotPackage,
    ShotDraft,
    ShotPlanDraft,
    ShotSpec,
)


def _shot_spec(duration: int = 5, role: BeatRole = BeatRole.hook) -> ShotSpec:
    return ShotSpec(
        beat_role=role,
        motion_tag=MotionTag.character_consistency,
        scene_line="Slow crane-up, she lifts her head on the final second. Audio: rain patter.",
        duration_seconds=duration,
        narration_line="She waited for the signal.",
        characters_in_frame=["Eve"],
    )


def _package(durations: list[int]) -> MultiShotPackage:
    return MultiShotPackage(
        shots=[_shot_spec(duration=d) for d in durations],
        style_anchor="Cel-shaded TV anime, thick clean line art, muted broadcast palette.",
        hook_text="the scene they cut",
        caption="they owed us this scene",
        hashtags=["anime", "fyp"],
        music_brief="slow strings building to a single piano hit",
    )


def _draft(duration: int = 5) -> ShotDraft:
    return ShotDraft(
        beat_role=BeatRole.build,
        motion_tag=MotionTag.spectacle,
        motion_intent="Camera pushes toward the tower as lights ignite floor by floor.",
        duration_seconds=duration,
        narration_line=None,
        characters_in_frame=[],
    )


def _plan(durations: list[int]) -> ShotPlanDraft:
    return ShotPlanDraft(
        shots=[_draft(duration=d) for d in durations],
        style_anchor="Cel-shaded TV anime, thick clean line art.",
        hook_text="the scene they cut",
        caption="caption",
        hashtags=["tag"],
        music_brief=None,
    )


# --- cardinality bounds -----------------------------------------------------


def test_package_two_shots_rejected():
    with pytest.raises(ValidationError):
        _package([6, 6])


def test_package_seven_shots_rejected():
    with pytest.raises(ValidationError):
        _package([4] * 7)


def test_package_three_shots_accepted():
    assert len(_package([4, 4, 4]).shots) == 3


def test_package_five_shots_accepted():
    assert len(_package([4, 4, 4, 4, 4]).shots) == 5


def test_package_six_shots_rejected():
    with pytest.raises(ValidationError):
        _package([4, 4, 4, 4, 4, 4])


# --- per-shot duration bounds -------------------------------------------------


def test_shot_duration_one_second_rejected():
    with pytest.raises(ValidationError):
        _shot_spec(duration=1)


def test_shot_duration_nine_seconds_rejected():
    with pytest.raises(ValidationError):
        _shot_spec(duration=9)


# --- total-duration envelope --------------------------------------------------


def test_package_total_26s_rejected():
    with pytest.raises(ValidationError):
        _package([8, 8, 6, 4])


def test_package_total_25s_accepted():
    assert sum(s.duration_seconds for s in _package([8, 8, 5, 4]).shots) == 25


def test_package_total_12s_accepted():
    assert sum(s.duration_seconds for s in _package([4, 4, 4]).shots) == 12


def test_package_total_10s_accepted():
    # The new floor (D1): one 10s Seedance generation must validate.
    assert sum(s.duration_seconds for s in _package([4, 4, 2]).shots) == 10


def test_package_total_9s_rejected():
    # Below the 10s floor — constructible now that the per-shot floor is 2s.
    with pytest.raises(ValidationError):
        _package([3, 3, 3])


def test_plan_draft_total_26s_rejected():
    with pytest.raises(ValidationError):
        _plan([8, 8, 6, 4])


def test_plan_draft_total_25s_accepted():
    assert sum(s.duration_seconds for s in _plan([8, 8, 5, 4]).shots) == 25


# --- MotionTag <-> yaml routing-key parity (D5) --------------------------------


def test_motion_tag_values_are_yaml_routing_keys():
    routing_keys = set(RenderRules().data["routing"].keys())
    for tag in MotionTag:
        assert tag.value in routing_keys, (
            f"MotionTag.{tag.name} = {tag.value!r} has no routing entry in "
            "config/render_rules.yaml — D5 requires verbatim parity"
        )


def test_spectacle_routes_seedance_first():
    assert RenderRules().route("spectacle") == ["seedance_2_0", "kling3_0"]


def test_max_shots_accessor_reads_yaml():
    rules = RenderRules()
    assert rules.max_shots("kling3_0") == 6
    assert rules.max_shots("seedance_2_0") == 10
    with pytest.raises(KeyError):
        rules.max_shots("veo3_1")  # single-shot-only model: no max_shots entry


# --- extra="forbid" guard -------------------------------------------------------


def test_shot_spec_rejects_unknown_field():
    with pytest.raises(ValidationError):
        ShotSpec(
            beat_role=BeatRole.hook,
            motion_tag=MotionTag.character_consistency,
            scene_line="y. Audio: z.",
            duration_seconds=5,
            narration_line=None,
            characters_in_frame=[],
            hallucinated_field="nope",
        )


def test_package_rejects_unknown_field():
    with pytest.raises(ValidationError):
        MultiShotPackage(
            shots=[_shot_spec(), _shot_spec(), _shot_spec()],
            style_anchor="s",
            hook_text=None,
            caption="c",
            hashtags=[],
            music_brief=None,
            mood_anchor="legacy field from the single-shot schema",
        )


def test_plan_draft_rejects_unknown_field():
    with pytest.raises(ValidationError):
        ShotPlanDraft(
            shots=[_draft(), _draft(), _draft()],
            style_anchor="s",
            hook_text=None,
            caption="c",
            hashtags=[],
            music_brief=None,
            onscreen_text=["legacy field"],
        )


# --- silent-beat passthrough + code-set defaults --------------------------------


def test_narration_none_is_valid_silent_beat():
    spec = ShotSpec(
        beat_role=BeatRole.establish,
        motion_tag=MotionTag.fluid_motion,
        scene_line="y. Audio: z.",
        duration_seconds=4,
        narration_line=None,
        characters_in_frame=[],
    )
    assert spec.narration_line is None


def test_package_code_set_defaults():
    package = _package([4, 4, 4])
    assert package.pitch_id is None
    assert package.reference_image_paths == []
    assert package.shots[0].model_cli_id == ""
    # Location grounding is opt-in: an ungrounded package defaults to empty
    # carriers (backward-compat with pre-grounding packages).
    assert package.world_anchor == ""
    assert package.location_reference_paths == []


def test_package_accepts_location_fields():
    package = _package([4, 4, 4])
    package.world_anchor = "A grand ice-tower chamber, pale marble floor."
    package.location_reference_paths = ["refs/_location/elfie_bedroom/room.jpg"]
    restored = MultiShotPackage.model_validate_json(package.model_dump_json())
    assert restored.world_anchor.startswith("A grand ice-tower")
    assert restored.location_reference_paths == ["refs/_location/elfie_bedroom/room.jpg"]


def test_package_round_trip_json():
    package = _package([5, 5, 5])
    restored = MultiShotPackage.model_validate_json(package.model_dump_json())
    assert restored == package


# Legacy single-shot tests deleted 2026-07-05 with the Shot/ContentPackage classes.
