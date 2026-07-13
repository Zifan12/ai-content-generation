"""Pydantic schema for a single render-adapter job.

A :class:`RenderJob` is the typed, model-agnostic description of ONE unit of
render work — the output the :class:`RenderAdapter` produces and a future
(P3.5) executor consumes. It is a pure data container: it carries everything
the executor needs to issue one Higgsfield call, but it never calls the CLI
itself and holds no behaviour.

Three job kinds flow through the pipeline (spec data-flow §7):

- ``"still"`` — a text-to-image render (e.g. nano_banana_2). No input image,
  no duration; ``image_ref`` / ``start_image`` / ``end_image`` / ``duration``
  are all ``None``.
- ``"motion"`` — an image-to-video render that animates a previously rendered
  still. ``image_ref`` points at that still; the prompt is motion-only.
- ``"keyframe"`` — a start+end interpolation render. ``start_image`` and
  ``end_image`` carry the two frames to interpolate between (the escalation
  lever for impossible-physics / event shots).

Field invariants (e.g. a still must not carry a duration) are enforced by the
adapter that builds these jobs, not by this schema — the schema stays a dumb,
permissive container so the adapter is the single source of correctness.
"""

from typing import Literal

from pydantic import BaseModel


class RenderJob(BaseModel):
    """One unit of render work, model-agnostic and executor-ready.

    Attributes:
        model_cli_id: The exact Higgsfield CLI model token the executor will
            pass through (e.g. ``"nano_banana_2"``, ``"veo3_1"``,
            ``"minimax_hailuo"``). The router selects this from
            ``config/render_rules.yaml``; it is a plain string, not an enum,
            so the valid set lives in the yaml rather than this schema.
        kind: Which of the three job types this is — ``"still"``, ``"motion"``,
            or ``"keyframe"`` — which determines how the executor wires images
            and duration.
        prompt: The model-native prompt string the builder produced. For
            ``"motion"`` jobs this is motion-only (it does not re-describe the
            still).
        image_ref: Reference (id/path) to the input still for an image-to-video
            ``"motion"`` job; ``None`` for stills and keyframes.
        start_image: Reference to the start frame for a ``"keyframe"`` job;
            ``None`` otherwise.
        end_image: Reference to the end frame for a ``"keyframe"`` job;
            ``None`` otherwise.
        aspect_ratio: Output aspect ratio string (e.g. ``"9:16"``).
        duration: Clip length in seconds for video jobs; ``None`` for stills.
            The adapter caps this at the chosen model's ``max_seconds``.
        shot_index: Zero-based index of the shot this job belongs to within the
            content package, used to order and group jobs back into shots. For
            ``"multi_shot"`` jobs this is the first covered shot's index.
        reference_images: Key-art paths/upload-ids grounding a ``"still"`` job
            (mandatory grounding, DECISIONS_LOCKED L3); empty for video jobs.
            CLI 1.1.5: repeated ``--image-references``, max 14.
        covers_shots: All shot indices a ``"multi_shot"`` job renders (one Kling
            generation with internal cuts); empty list for single-shot jobs,
            meaning "just shot_index".
        prompt_english: The pre-translation English composition when ``prompt``
            was translated (D-language, spec 2026-07-13); ``None`` means
            ``prompt`` was never translated (English lane or translation
            fallback — disambiguate via ``translation_status``).
        translation_status: Provenance of the prompt language, set by the
            prompt-translation stage: ``"not_attempted"`` (leaf absent/en, or
            stage never ran), ``"translated"`` (prompt is Chinese,
            ``prompt_english`` holds the mirror), or ``"fallback:<check>"``
            (translation discarded by the named mechanical check; prompt is
            the original English). Dumped run JSONs self-explain via this
            field — the console WARNING alone is not durable.
    """

    model_cli_id: str
    kind: Literal["still", "motion", "keyframe", "multi_shot"]
    prompt: str
    image_ref: str | None = None
    start_image: str | None = None
    end_image: str | None = None
    aspect_ratio: str
    duration: int | None = None
    shot_index: int
    reference_images: list[str] = []
    covers_shots: list[int] = []
    prompt_english: str | None = None
    translation_status: str = "not_attempted"
