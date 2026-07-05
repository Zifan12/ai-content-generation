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
        motion_prompt=f"MOTION[{index}] slow push-in, she turns. Audio: rain.",
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
