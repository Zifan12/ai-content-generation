"""
Angle-diverse final ranking for the reference harvester (Task 10).

Turns judged frames into the approved reference set. Two-stage decision:

1. Eligibility (decision D1 — defensive): a frame must carry a verdict AND
   pass every component check, not just the judge's composite ``usable``
   flag. ``usable`` is re-derived here from ``character_present``,
   ``text_or_watermark_overlap`` and ``single_character`` because the judge
   is an uncalibrated LLM — if its composite ever disagrees with its own
   component observations, the strictest reading wins. A frame with
   ``verdict=None`` (never judged) is never eligible.

2. Selection (decision D2 — angle coverage before depth): the playbook
   (ai_video_resources/reference-material-playbook.md §3) says front +
   three-quarter + profile coverage beats N best frontals — near-duplicate
   angles actively harm via averaging. So round 1 takes the sharpest frame
   from each CORE angle bucket in fixed priority order (front,
   three_quarter, profile); ``back`` and ``unknown`` are NOT coverage-worthy
   core buckets (a back view carries no face identity; unknown carries no
   angle signal) and only fill remaining slots in round 2, where all
   unselected eligible frames compete purely on sharpness (decision D3
   tie-break) up to ``k_max``.

Decision D4: ``k_min`` is a SIGNAL, not a gate — fewer eligible frames than
``k_min`` still returns everything found; the orchestrator (Task 11) decides
what status that shortfall maps to. This function never raises on shortfall.
"""

from src.reference.schemas import FrameScore

# Core coverage buckets in pick priority (playbook §3). back/unknown excluded
# deliberately — they fill only after coverage, on sharpness alone.
_CORE_ANGLES = ("front", "three_quarter", "profile")


def _eligible(frame: FrameScore) -> bool:
    """A frame is eligible only when judged AND every component check passes
    (defensive D1 — the judge's composite ``usable`` is not trusted alone)."""
    verdict = frame.verdict
    if verdict is None:
        return False
    return (
        verdict.usable
        and verdict.character_present
        and not verdict.text_or_watermark_overlap
        and verdict.single_character
    )


def select_top(
    frames: list[FrameScore],
    *,
    k_min: int,
    k_max: int,
) -> list[FrameScore]:
    """
    Pick the approved reference set from judged frames, favoring angle
    coverage over raw sharpness.

    Round 1 takes the sharpest eligible frame per core angle (front,
    three_quarter, profile — in that priority order); round 2 fills the
    remaining slots up to ``k_max`` with the next-sharpest unselected
    eligible frames from ANY angle (including back/unknown). Sharpness ties
    break on path (ascending) so the result is fully deterministic.

    Args:
        frames: judged FrameScore entries (verdict may be None for frames
            the judge never saw — those are dropped).
        k_min: desired minimum — a SIGNAL only (D4); fewer eligible frames
            than this still returns what exists, and the orchestrator maps
            the shortfall to a status.
        k_max: hard cap on returned frames.

    Returns:
        At most ``k_max`` FrameScore entries, sorted sharpest-first
        (path-ascending on ties). Empty list when nothing is eligible.
    """
    eligible = [f for f in frames if _eligible(f)]
    # Sharpest first; path breaks ties so ordering never depends on input order.
    eligible.sort(key=lambda f: (-f.sharpness, f.path))

    selected: list[FrameScore] = []
    picked_paths: set[str] = set()

    for angle in _CORE_ANGLES:
        if len(selected) >= k_max:
            break
        for frame in eligible:
            assert frame.verdict is not None  # _eligible guarantees this
            if frame.verdict.angle == angle and frame.path not in picked_paths:
                selected.append(frame)
                picked_paths.add(frame.path)
                break

    for frame in eligible:
        if len(selected) >= k_max:
            break
        if frame.path not in picked_paths:
            selected.append(frame)
            picked_paths.add(frame.path)

    selected.sort(key=lambda f: (-f.sharpness, f.path))
    return selected
