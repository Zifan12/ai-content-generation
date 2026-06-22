from unittest.mock import MagicMock

import pytest

from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob
from src.schemas.generation import ContentPackage, Shot
from src.generation.render_adapters.adapter import render_jobs

# ---------------------------------------------------------------------------
# Fixtures for render_jobs() conformance tests.
#
# The package is a valid 3-shot chained-continuity ContentPackage shaped to
# exercise every branch of render_jobs in ONE call:
#
#   - shot 0 (opener) carries start_keyframe -> should emit a STILL job.
#     Its motion says "water" -> classify_motion -> "fluid_motion" -> routes
#     to minimax_hailuo (a built model).
#   - shot 1 (inheritor) has NO start_keyframe, NO end_keyframe -> a plain
#     MOTION job only.
#   - shot 2 (inheritor) carries end_keyframe AND its motion says "edges stay"
#     -> classify_motion -> "impossible_physics" -> the KEYFRAME-job branch
#     should fire (impossible + end_keyframe).
#
# Both candidate "is this shot impossible/event?" signals are present, so the
# fixture works whichever one render_jobs ends up reading: the routing tag
# (motion text triggers "impossible_physics") and the package device
# ("transformation", an event-style device).
#
# `available` is restricted to the two models that actually have builders, so
# the router can never pick a model render_jobs has no builder for.
# ---------------------------------------------------------------------------

BUILT_MODELS = {"minimax_hailuo", "veo3_1"}


@pytest.fixture
def rules() -> RenderRules:
    """Real RenderRules loaded from config/render_rules.yaml (routing + caps are data, not logic)."""
    return RenderRules()


@pytest.fixture
def builders() -> dict[str, MagicMock]:
    """A {cli_id: builder} map of mocked PromptBuilders.

    Each builder exposes build_still_prompt / build_motion_prompt as MagicMocks
    returning a recognizable sentinel string (matching the real PromptBuilder
    ABC, which has exactly those two methods). The adapter test asserts on the
    INPUT wiring (which builder was called) and on the assembled RenderJob,
    never on real LLM output. A keyframe job reuses the motion prompt — the ABC
    has no separate keyframe method — so no third mock method is needed.
    """
    def _mock_builder(cli_id: str) -> MagicMock:
        b = MagicMock(name=f"builder[{cli_id}]")
        b.build_still_prompt.return_value = f"STILL_PROMPT::{cli_id}"
        b.build_motion_prompt.return_value = f"MOTION_PROMPT::{cli_id}"
        return b

    return {cli_id: _mock_builder(cli_id) for cli_id in BUILT_MODELS}


@pytest.fixture
def package() -> ContentPackage:
    """A valid 3-shot package exercising still + motion + keyframe branches.

    See module-level fixture comment for which shot trips which branch.
    """
    return ContentPackage(
        shots=[
            # Shot 0 (opener) trips ALL THREE branches at once:
            #   - start_keyframe set  -> STILL job (the one generated opening still)
            #   - motion always       -> MOTION job
            #   - end_keyframe set + "edges stay"/"defying" motion (impossible_physics)
            #     -> KEYFRAME job (start+end interpolation).
            # The keyframe-escalated shot is the OPENER on purpose: the first-last-frame
            # technique needs a real start image AND a real end image (ai_video_resources/
            # image-video-director/03 L36-37), and the chain contract only permits a
            # start_keyframe on segment 1. Inheritor shots (no start frame) therefore
            # cannot be keyframe-escalated — there'd be no start image to interpolate from.
            Shot(
                start_keyframe=(
                    "low-angle medium shot, a backyard swimming pool brimming to the lip, "
                    "still surface, midday overcast daylight from above"
                ),
                end_keyframe=(
                    "the same pool a moment later, water drained to a vertical wall yet the "
                    "edges stay full, the impossible level frozen"
                ),
                motion="water drains inward while the edges stay full, defying gravity",
            ),
            Shot(
                start_keyframe=None,
                end_keyframe=None,
                motion="slow push-in toward the deep end, ambient drift continuing",
            ),
            Shot(
                start_keyframe=None,
                end_keyframe=None,
                motion="the water surface ripples once, gentle current drifting toward the far edge",
            ),
        ],
        device="transformation",
        device_rationale="The pool's impossible drain is the single transforming spectacle.",
        mood_anchor="muted overcast palette, soft top light, photoreal with faint grain, quiet uncanny",
        onscreen_text=[],
        caption="this pool breaks physics",
        hashtags=["surreal", "veo3", "uncannyvalley"],
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
        shot_index=0
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


def test_render_jobs_emits_correct_jobs_per_shot(package, rules, builders):
    """render_jobs translates one ContentPackage into the right RenderJob orders.

    This is the RED test (TDD): it imports and calls render_jobs, which does not
    exist yet in adapter.py — so this test fails until you implement it. Notice
    how the fixtures (package, rules, builders) arrive as PARAMETERS: pytest
    matches each parameter name to a @pytest.fixture function above and injects
    the return value. You never call package() yourself.

    The fixture package has 3 shots:
      - shot 0: start_keyframe + end_keyframe + "edges stay"/"defying" motion
        (impossible_physics -> hailuo). Trips all three job kinds.
      - shot 1: plain inheritor (no keyframes)
      - shot 2: plain inheritor (no keyframes)

    Expected output (the contract render_jobs must satisfy):
      - 1 STILL job   (only shot 0 has a start_keyframe)
      - 3 MOTION jobs (every shot becomes an animated clip)
      - 1 KEYFRAME job (only shot 0: end_keyframe + impossible)
      => 5 jobs total.
    """

    jobs = render_jobs(package, rules, builders, available=BUILT_MODELS)

    # --- headline: total count and per-kind breakdown ---
    assert len(jobs) == 5
    kinds = [j.kind for j in jobs]
    assert kinds.count("still") == 1
    assert kinds.count("motion") == 3
    assert kinds.count("keyframe") == 1

    # --- still job: belongs to shot 0, carries no duration, no input image ---
    still = next(j for j in jobs if j.kind == "still")
    assert still.shot_index == 0
    assert still.duration is None
    assert still.image_ref is None

    # --- routing: the impossible shot's motion job went to the physics king ---
    impossible_motion = next(
        j for j in jobs if j.kind == "motion" and j.shot_index == 0
    )
    assert impossible_motion.model_cli_id == "minimax_hailuo"

    # --- keyframe job: belongs to shot 0 and carries both frames to interpolate ---
    keyframe = next(j for j in jobs if j.kind == "keyframe")
    assert keyframe.shot_index == 0
    assert keyframe.start_image is not None
    assert keyframe.end_image is not None

    # --- duration cap: no motion clip exceeds its model's max_seconds ---
    for j in jobs:
        if j.kind in {"motion", "keyframe"}:
            assert j.duration is not None
            assert j.duration <= rules.max_seconds(j.model_cli_id)

    # --- prompts came from the builders (not real LLM), proving dispatch wiring ---
    assert still.prompt.startswith("STILL_PROMPT::")
    for j in jobs:
        if j.kind == "motion":
            assert j.prompt.startswith("MOTION_PROMPT::")