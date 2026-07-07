"""Tests for the v3 render adapter (plan 2026-07-04 Task 5).

The load-bearing test here is composition order + constraint presence — the test
that proves audit issue 10's second half is closed (global_constraints reaches
every prompt) and that anchors/style are appended in code, byte-identical, per
D10. The fixture package mirrors spec §7 Stage-3 criterion 1: one 3-shot Kling
consistency group + one Veo breakout.
"""

import pytest

from src.generation.render_adapters.adapter import STILL_MODEL, render_jobs
from src.generation.render_adapters.rules import RenderRules
from src.monitor.schemas import BeatRole
from src.schemas.generation import MotionTag, MultiShotPackage, ShotSpec

ANCHORS = "ANCHORS: Eve — short tousled dark-brown hair, pure-white armored bodysuit."
STYLE = "STYLE: cel-shaded TV anime, thick clean line art."


def _shot(
    index: int,
    *,
    tag: MotionTag = MotionTag.character_consistency,
    model: str = "kling3_0",
    duration: int = 4,
) -> ShotSpec:
    return ShotSpec(
        beat_role=BeatRole.build,
        motion_tag=tag,
        still_prompt=f"STILL[{index}] low angle, subject centered.",
        scene_line=f"MOTION[{index}] slow push-in, she turns. Audio: rain.",
        duration_seconds=duration,
        narration_line=None,
        characters_in_frame=["Eve"],
        model_cli_id=model,
    )


@pytest.fixture(scope="module")
def rules():
    return RenderRules()


@pytest.fixture()
def package():
    """One 3-shot kling group + one veo breakout (spec §7 Stage-3 criterion 1)."""
    return MultiShotPackage(
        shots=[
            _shot(0),
            _shot(1),
            _shot(2),
            _shot(3, tag=MotionTag.fluid_motion, model="veo3_1", duration=6),
        ],
        style_anchor=STYLE,
        anchors_block=ANCHORS,
        hook_text="hook",
        caption="caption",
        hashtags=["tag"],
        music_brief=None,
        reference_image_paths=["refs/eve_1.jpg", "refs/eve_2.jpg"],
        consistency_groups=[[0, 1, 2], [3]],
    )


def test_job_shape_group_plus_breakout(package, rules):
    jobs = render_jobs(package, rules)
    kinds = [(job.kind, job.model_cli_id) for job in jobs]
    assert kinds == [
        ("still", STILL_MODEL),
        ("multi_shot", "kling3_0"),
        ("still", STILL_MODEL),
        ("motion", "veo3_1"),
    ]


def test_still_jobs_carry_grounding_refs(package, rules):
    stills = [job for job in render_jobs(package, rules) if job.kind == "still"]
    assert len(stills) == 2
    for job in stills:
        assert job.reference_images == ["refs/eve_1.jpg", "refs/eve_2.jpg"]


def test_still_prompt_composition_order(package, rules):
    still = render_jobs(package, rules)[0]
    prompt = still.prompt
    # anchors -> shot still_prompt -> style -> every still-kind constraint string
    assert prompt.index(ANCHORS) < prompt.index("STILL[0]") < prompt.index(STYLE)
    for constraint in rules.global_constraints("still", style=STYLE):
        assert constraint in prompt
    # [STYLE] placeholder resolved: style_consistency bucket carries the anchor
    assert f"hold {STYLE} throughout" in prompt


def test_motion_prompts_carry_motion_constraints_only(package, rules):
    jobs = render_jobs(package, rules)
    for job in jobs:
        if job.kind in ("motion", "multi_shot"):
            for constraint in rules.global_constraints("motion", style=""):
                assert constraint in job.prompt
            assert ANCHORS not in job.prompt  # i2v rule: no identity restating
            assert STYLE not in job.prompt


def test_multi_shot_prompt_labels_and_timestamps_computed_in_code(package, rules):
    group_job = render_jobs(package, rules)[1]
    assert group_job.kind == "multi_shot"
    assert "Shot 1 (0-4s): MOTION[0]" in group_job.prompt
    assert "Shot 2 (4-8s): MOTION[1]" in group_job.prompt
    assert "Shot 3 (8-12s): MOTION[2]" in group_job.prompt
    assert group_job.duration == 12
    assert group_job.covers_shots == [0, 1, 2]
    assert group_job.shot_index == 0


def test_singleton_motion_duration_capped_by_model(rules):
    package = MultiShotPackage(
        shots=[
            _shot(0, tag=MotionTag.fluid_motion, model="veo3_1", duration=4),
            _shot(1, tag=MotionTag.fluid_motion, model="veo3_1", duration=4),
            _shot(2, tag=MotionTag.fluid_motion, model="veo3_1", duration=8),
        ],
        style_anchor=STYLE,
        anchors_block=ANCHORS,
        hook_text=None,
        caption="c",
        hashtags=[],
        music_brief=None,
        reference_image_paths=["r.jpg"],
        consistency_groups=[[0], [1], [2]],
    )
    jobs = render_jobs(package, rules)
    motion_jobs = [job for job in jobs if job.kind == "motion"]
    assert [job.duration for job in motion_jobs] == [4, 4, 8]
    assert all(job.duration <= rules.max_seconds("veo3_1") for job in motion_jobs)


def test_group_still_uses_first_members_still_prompt(package, rules):
    jobs = render_jobs(package, rules)
    assert "STILL[0]" in jobs[0].prompt
    assert "STILL[1]" not in jobs[0].prompt  # one seed still per group, from shot 1


def test_emits_audio_accessors_still_work(rules):
    assert rules.emits_audio("veo3_1") is True
    assert rules.emits_audio("nano_banana_2") is False


# --- SCENE LANE (spec 2026-07-06 A3/D3) -------------------------------------------
# A package with EMPTY consistency_groups — the only kind the scene-lane writer
# produces — must yield ONE composed multi_shot job. Legacy grouped packages
# above keep exercising the old still-first branch untouched (D4).


def _scene_shot(index: int, characters: list[str]) -> ShotSpec:
    return ShotSpec(
        beat_role=BeatRole.build,
        motion_tag=MotionTag.character_consistency,
        scene_line=f"LINE[{index}] Camera: slow push-in. Audio: rain.",
        duration_seconds=4,  # 3 shots x 4s = 12s, inside the 10-25 envelope
        narration_line=None,
        characters_in_frame=characters,
    )


def _scene_package(
    shots: list[ShotSpec] | None = None,
    refs: list[str] | None = None,
) -> MultiShotPackage:
    return MultiShotPackage(
        shots=shots
        or [
            _scene_shot(0, ["Eve"]),
            _scene_shot(1, ["Eve", "Adam"]),
            _scene_shot(2, ["Adam"]),
        ],
        style_anchor=STYLE,
        anchors_block=ANCHORS,
        hook_text=None,
        caption="c",
        hashtags=[],
        music_brief=None,
        reference_image_paths=refs
        if refs is not None
        else [
            # deliberately unsorted within Adam's folder — the adapter sorts
            "refs/adam/b_profile.png",
            "refs/adam/a_front.png",
            "refs/eve/front.png",
        ],
    )


def test_scene_package_yields_one_multi_shot_job(rules):
    jobs = render_jobs(_scene_package(), rules)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.kind == "multi_shot"
    assert job.model_cli_id == rules.scene_model()
    assert job.covers_shots == [0, 1, 2]
    assert job.duration == 10  # scene_lane.defaults.duration_seconds, under the cap
    assert job.aspect_ratio == "9:16"


def test_scene_refs_ordered_cast_first_appearance_then_filename(rules):
    job = render_jobs(_scene_package(), rules)[0]
    # Eve appears first (shot 0) so her refs upload first; Adam's sort by filename.
    assert job.reference_images == [
        "refs/eve/front.png",
        "refs/adam/a_front.png",
        "refs/adam/b_profile.png",
    ]
    # binding is TEXTUAL and positional — the prompt names each character's slots
    assert "Eve is the character shown in image1." in job.prompt
    assert "Adam is the character shown in image2, image3." in job.prompt


def test_scene_prompt_composition_order_and_single_tail(rules):
    job = render_jobs(_scene_package(), rules)[0]
    prompt = job.prompt
    # A3 order: style preamble -> identity (anchors + bindings) -> body -> tail
    positions = [
        prompt.index("Exactly matching the art style"),
        prompt.index(ANCHORS),
        prompt.index("LINE[0]"),
        prompt.index("No music."),
    ]
    assert positions == sorted(positions)
    # joined as one continuous scene: N-1 cuts, tail lines exactly once
    assert prompt.count("Then cut to:") == 2
    assert prompt.count("No music.") == 1
    assert prompt.count("Generate the video without subtitles.") == 1  # quality suffix
    # anchors travel via composition, not via the LLM's lines
    assert prompt.count(ANCHORS) == 1


def test_scene_char_cap_violation_raises(rules):
    shots = [
        _scene_shot(0, ["Eve", "Adam"]),
        _scene_shot(1, ["Bea", "Cal"]),
        _scene_shot(2, ["Eve"]),
    ]
    refs = [
        "refs/eve/f.png",
        "refs/adam/f.png",
        "refs/bea/f.png",
        "refs/cal/f.png",
    ]
    with pytest.raises(ValueError, match="max_characters_in_scene"):
        render_jobs(_scene_package(shots=shots, refs=refs), rules)


def test_scene_unattributed_ref_crashes_loud(rules):
    refs = [
        "refs/eve/front.png",
        "refs/adam/front.png",
        "render_taste_test/wistoria_refs/will_2_adult.png",  # flat legacy layout
    ]
    with pytest.raises(ValueError, match="matches no\s+cast member"):
        render_jobs(_scene_package(refs=refs), rules)


def test_scene_ungrounded_cast_member_crashes_loud(rules):
    refs = ["refs/eve/front.png"]  # Adam has no sheet
    with pytest.raises(ValueError, match="no reference images"):
        render_jobs(_scene_package(refs=refs), rules)


def test_scene_prompt_over_char_ceiling_raises(rules):
    long_shots = [
        ShotSpec(
            beat_role=BeatRole.build,
            motion_tag=MotionTag.character_consistency,
            scene_line="x" * 1200 + f" LINE[{i}]. Audio: rain.",
            duration_seconds=4,
            narration_line=None,
            characters_in_frame=["Eve"],
        )
        for i in range(3)
    ]
    refs = ["refs/eve/front.png"]
    with pytest.raises(ValueError, match="max_prompt_chars"):
        render_jobs(_scene_package(shots=long_shots, refs=refs), rules)
