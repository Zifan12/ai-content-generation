"""End-to-end dry-run of the multi-shot text pipeline: pitch → writer → adapter → executor.

FakeLLM drives the two writer calls; a fake CLI runner answers every cost query.
No network, no credits — this pins the SHAPE of the whole Stage-2 path: a judged
StoryPitch becomes composed, grouped, costed render jobs.
"""

from src.generation.content_writer import ContentWriter, DialectConversion
from src.generation.executor import execute
from src.generation.render_adapters.adapter import STILL_MODEL, render_jobs
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
        if response_model is DialectConversion:
            n = prompt.count("motion_intent:")
            return DialectConversion(
                motion_prompts=[f"converted {i}. Audio: rain." for i in range(n)]
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
        pitch, rules=rules, reference_image_paths=["refs/eve.jpg"], pitch_id=1
    )
    assert package.consistency_groups == [[0, 1, 2]]

    jobs = render_jobs(package, rules)
    assert [job.kind for job in jobs] == ["still", "multi_shot"]
    assert jobs[0].model_cli_id == STILL_MODEL
    assert jobs[0].reference_images == ["refs/eve.jpg"]
    assert jobs[1].model_cli_id == "kling3_0"
    assert jobs[1].duration == 12

    result = execute(jobs, str(tmp_path), dry_run=True, run_cli=_fake_cli)
    assert result.credits_spent == 15.0  # 2 jobs x fake 7.5
    assert result.still_paths == [] and result.clips == []
