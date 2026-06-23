"""Shared ContentPackage builders for eval and rubric tests."""

from src.schemas.generation import ContentPackage, Shot


def baseline_package() -> ContentPackage:
    """
    Return a fresh, schema-valid chained ContentPackage that passes every check.

    A new object is built on every call so a test that mutates one field cannot
    leak into the next. The defaults are deliberately "clean": segment 1 holds the
    only start_keyframe (no palette vocab), segments 2-3 inherit (start_keyframe
    None), every motion is movement-only, no field carries scale/quality words, and
    the package mood_anchor is the single grade source.

    DEVICE CHOICE (matters): device is "encounter", NOT transformation /
    time_compression. The device_requires_event_beat check only fires for those two
    change-devices; picking encounter keeps the baseline outside that conditional, so
    the baseline passes cleanly and each test drives exactly one criterion.
    """
    shots = [
        Shot(
            start_keyframe="wide shot, harbor at dawn, fishing boats moored",
            motion="slow push in over 5s, ending as the lone mast fills the frame",
        ),
        Shot(motion="gulls scatter off the mast as the camera drifts left toward open water"),
        Shot(motion="hold on the water, faint shimmer, settling into stillness"),
    ]
    return ContentPackage(
        shots=shots,
        device="encounter",
        device_rationale="A second presence (the gulls) enters mid-drift; the take is the meeting.",
        mood_anchor="cold teal light, photoreal, faintly uncanny",
        onscreen_text=[],
        caption="dawn at the harbor",
        hashtags=["#surreal", "#harbor"],
    )
