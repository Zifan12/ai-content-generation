"""Thin render adapter: turn a single-shot ContentPackage into render jobs.

The writer (src/generation/content_writer.py) now emits model-native prompts and
picks the motion model itself, so this adapter holds no router and no prompt
builders — it is pure plumbing. It packages the two strings the writer already
produced (the opening-still prompt and the motion prompt) into two typed
RenderJobs the executor (Task 6) can run: a nano_banana_2 still, then an
image-to-video motion clip on the package's chosen model.

There is no per-shot loop (a single-shot package has exactly one shot), no
keyframe-escalation branch, and no model selection here — all of that moved
upstream into the writer or away entirely with the retired 3-segment paradigm.
"""

from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob
from src.schemas.generation import ContentPackage

# The opening still is an IMAGE render, not a video one — it has no entry in the
# yaml routing table (which ranks VIDEO models). nano_banana_2 is the project's
# standard photoreal opening-still model.
STILL_MODEL = "nano_banana_2"

# Product cap: the single-shot clip is ~8s regardless of how long a model COULD
# run. Some models cap higher (Veo 8, Kling 15, Seedance 20); we still want 8s,
# so the duration is the smaller of this cap and the model's own max_seconds.
DEFAULT_CLIP_SECONDS = 8


def render_jobs(package: ContentPackage, rules: RenderRules) -> list[RenderJob]:
    """Translate a single-shot ContentPackage into its two render jobs.

    Produces exactly two jobs, in execution order:

    1. A ``"still"`` job on ``STILL_MODEL`` (nano_banana_2). Its prompt is the
       shot's ``start_keyframe`` with the package ``mood_anchor`` appended —
       the mood_anchor is the package-level grade kept separate by the writer so
       it can be applied to the still (and any end_keyframe) at render time.
       Stills carry no duration.
    2. A ``"motion"`` job on the package's chosen ``model_cli_id``. Its prompt is
       the shot's already-model-native ``motion`` string (which includes the
       Audio: line). Duration is capped at the smaller of DEFAULT_CLIP_SECONDS
       and the model's own ``max_seconds`` so the clip stays ~8s.

    Both jobs use ``shot_index=0`` (one shot) and ``aspect_ratio="9:16"``.

    Args:
        package: The single-shot ContentPackage from the writer.
        rules: Loaded render rules, used for the motion model's max_seconds cap.

    Returns:
        A two-element list ``[still_job, motion_job]`` ready for the executor.
    """
    motion_model = package.model_cli_id

    still_job = RenderJob(
        model_cli_id=STILL_MODEL,
        kind="still",
        prompt=package.shot.start_keyframe + " " + package.mood_anchor,
        aspect_ratio="9:16",
        shot_index=0,
        duration=None,
    )

    motion_job = RenderJob(
        model_cli_id=motion_model,
        kind="motion",
        prompt=package.shot.motion,
        aspect_ratio="9:16",
        shot_index=0,
        duration=min(DEFAULT_CLIP_SECONDS, rules.max_seconds(motion_model)),
    )

    return [still_job, motion_job]
