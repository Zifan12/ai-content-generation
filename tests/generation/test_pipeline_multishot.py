"""End-to-end dry-run of the multi-shot text pipeline: pitch → writer → adapter → executor.

FakeLLM drives the two writer calls; a fake CLI runner answers every cost query.
No network, no credits — this pins the SHAPE of the whole Stage-2 path: a judged
StoryPitch becomes composed, grouped, costed render jobs.
"""

from src.generation.content_writer import ContentWriter, SceneLines
from src.generation.executor import execute
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
                style_anchor="cel-shaded anime register",
                anchors_block="Eve identity sentence.",
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
    assert argv[:3] == ["higgsfield", "generate", "cost"], (
        "dry run must never issue a create call"
    )
    return "7.5 credits"


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
    # Scene lane (D3/D4): no routing, no groups; every shot carries the one
    # configured scene model and its call-2 prose line.
    assert package.consistency_groups == []
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
    assert job.duration == 10  # scene_lane.defaults, capped at the CLI limit
    assert "Then cut to:" in job.prompt
    assert "Eve is the character shown in image1, image2." in job.prompt

    result = execute(jobs, str(tmp_path), dry_run=True, run_cli=_fake_cli)
    assert result.credits_spent == 7.5  # 1 job x fake 7.5
    assert result.still_paths == [] and result.clips == []
