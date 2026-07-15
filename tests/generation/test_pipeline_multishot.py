"""End-to-end dry-run of the multi-shot text pipeline: pitch → writer → adapter → executor.

FakeLLM drives the two writer calls; a fake CLI runner answers every cost query.
No network, no credits — this pins the SHAPE of the whole Stage-2 path: a judged
StoryPitch becomes composed, grouped, costed render jobs.
"""

from src.generation.content_writer import ContentWriter, SceneLines
from src.generation.executor import execute_scene, execute_splice
from src.generation.render_adapters.adapter import render_jobs
from src.generation.render_adapters.rules import RenderRules
from src.schemas.generation import (
    BeatRole,
    MotionTag,
    ShotDraft,
    ShotPlanDraft,
)
from tests.helpers.story_pitch import build_story_pitch


class FakeLLM:
    def parse(self, prompt, response_model, system=None, max_tokens=1024):
        if response_model is ShotPlanDraft:
            return ShotPlanDraft(
                shots=[
                    ShotDraft(
                        beat_role=BeatRole.build,
                        motion_tag=MotionTag.character_consistency,
                        motion_intent=f"intent {i}",
                        duration_seconds=4,
                        narration_line="line",
                        characters_in_frame=["Eve"],
                    )
                    for i in range(3)
                ],
                hook_text=None,
                caption="caption",
                hashtags=["tag"],
                music_brief=None,
            )
        if response_model is SceneLines:
            n = prompt.count("motion_intent:")
            return SceneLines(
                scene_lines=[f"converted {i}. Audio: rain." for i in range(n)]
            )
        raise AssertionError(response_model)


def _fake_cli(argv):
    raise AssertionError("scene dry run must make ZERO CLI calls")


def test_pitch_to_costed_jobs_dry_run(tmp_path):
    rules = RenderRules()
    pitch = build_story_pitch(3)

    package = ContentWriter(llm=FakeLLM()).write(
        pitch,
        rules=rules,
        # path convention: parent folder = character slug (refs/eve/...)
        reference_image_paths=["refs/eve/front.png", "refs/eve/profile.png"],
        pitch_id=1,
    )
    # Scene lane (D3): no routing; every shot carries the one configured
    # scene model and its call-2 prose line.
    assert {shot.model_cli_id for shot in package.shots} == {rules.scene_model()}
    assert [shot.scene_line for shot in package.shots] == [
        f"converted {i}. Audio: rain." for i in range(3)
    ]

    # ONE composed multi_shot scene job covering every shot (spec A3/D3).
    jobs = render_jobs(package, rules)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.kind == "multi_shot"
    assert job.model_cli_id == rules.scene_model()
    assert job.covers_shots == [0, 1, 2]
    assert job.reference_images == ["refs/eve/front.png", "refs/eve/profile.png"]
    assert job.duration == 15  # scene_lane.defaults (bumped 10->15, 2026-07-10), capped at the CLI limit
    assert "Then cut to:" in job.prompt
    assert "Eve is the character shown in image1, image2." in job.prompt

    result = execute_scene(job, str(tmp_path), dry_run=True, run_cli=_fake_cli, rules=rules)
    assert result.credits_spent == 67.5  # 15s x 4.5cr/s @720p, yaml-rate estimate (duration bumped 10->15, 2026-07-10)
    assert result.still_paths == [] and result.clips == []


def test_pitch_to_costed_jobs_dry_run_splice_lane(tmp_path, monkeypatch):
    """Same pitch, same writer, per_scene_splice lane: N shots -> N costed jobs.

    The lane is a CONFIG choice, so only scene_lane.mode changes here — nothing
    upstream of the adapter knows the difference. monkeypatch.setitem restores
    the mode so the yaml default (single_gen, Q1) can't leak into another test.
    """
    rules = RenderRules()
    monkeypatch.setitem(rules.data["scene_lane"], "mode", "per_scene_splice")
    pitch = build_story_pitch(3)

    package = ContentWriter(llm=FakeLLM()).write(
        pitch,
        rules=rules,
        reference_image_paths=["refs/eve/front.png", "refs/eve/profile.png"],
        pitch_id=1,
    )

    jobs = render_jobs(package, rules)
    assert len(jobs) == 3  # one standalone generation per shot, not one for all
    for i, job in enumerate(jobs):
        assert job.kind == "scene_shot"
        assert job.model_cli_id == rules.scene_model()
        assert job.covers_shots == [i]
        assert job.duration == 7  # scene_lane.splice_defaults, not the 15s single_gen default
        # Eve is in every shot, so every clip carries her refs and rebinds them
        assert job.reference_images == ["refs/eve/front.png", "refs/eve/profile.png"]
        assert "Eve is the character shown in image1, image2." in job.prompt
        assert f"converted {i}." in job.prompt
        assert "Then cut to:" not in job.prompt  # nothing to cut to inside one shot

    result = execute_splice(jobs, str(tmp_path), dry_run=True, run_cli=_fake_cli, rules=rules)
    # 3 shots x 7s x 4.5cr/s @720p = 94.5cr — pricier than single_gen's 67.5cr
    # for the same video (more billed seconds), which is the lane's known cost.
    assert result.credits_spent == 94.5
    assert result.still_paths == [] and result.clips == []
