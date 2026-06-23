import pytest

from src.generation.render_adapters.adapter import STILL_MODEL, render_jobs
from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob
from src.schemas.generation import ContentPackage, Shot

SINGLE_SHOT_CAP_SECONDS = 8


@pytest.fixture
def rules() -> RenderRules:
    return RenderRules()


@pytest.fixture
def package() -> ContentPackage:
    """Single-shot package — one shot, model_cli_id stamped by the writer."""
    return ContentPackage(
        shot=Shot(
            start_keyframe="Handheld phone POV, kitchen counter, glass mid-spill.",
            motion="Water freezes in place as it pours. Audio: sharp tap of ice forming.",
        ),
        model_cli_id="veo3_1",
        premise="Water freezes mid-pour in a normal kitchen.",
        mood_anchor="Cool daylight, desaturated phone footage, photoreal.",
        onscreen_text=["wait is this real??"],
        caption="I still don't know what I filmed.",
        hashtags=["surreal", "fyp"],
    )


def test_pydantic_model():
    still_render = RenderJob(
        model_cli_id="nano_banana_2",
        kind="still",
        prompt="test",
        image_ref=None,
        start_image=None,
        end_image=None,
        duration=None,
        aspect_ratio="9:16",
        shot_index=0,
    )

    assert still_render.model_dump() == {
        "model_cli_id": "nano_banana_2",
        "kind": "still",
        "prompt": "test",
        "image_ref": None,
        "start_image": None,
        "end_image": None,
        "duration": None,
        "aspect_ratio": "9:16",
        "shot_index": 0,
    }


def test_render_jobs_emits_two_jobs(package, rules):
    jobs = render_jobs(package, rules)

    assert len(jobs) == 2

    still = jobs[0]
    assert still.model_cli_id == STILL_MODEL
    assert still.kind == "still"
    assert still.shot_index == 0
    assert still.aspect_ratio == "9:16"
    assert still.duration is None
    assert still.prompt.endswith(package.mood_anchor)
    assert package.shot.start_keyframe in still.prompt

    motion = jobs[1]
    assert motion.model_cli_id == package.model_cli_id
    assert motion.kind == "motion"
    assert motion.shot_index == 0
    assert motion.aspect_ratio == "9:16"
    assert motion.prompt == package.shot.motion
    expected_duration = min(
        SINGLE_SHOT_CAP_SECONDS,
        rules.max_seconds(package.model_cli_id),
    )
    assert motion.duration == expected_duration


def test_emits_audio_veo3_1(rules):
    assert rules.emits_audio("veo3_1") is True


def test_emits_audio_still_model_returns_false(rules):
    assert rules.emits_audio("nano_banana_2") is False
