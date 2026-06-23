"""
Tests for the deterministic ("code-check") rubric criteria, chain grammar (Task 2).

Each criterion is a pure function over a ContentPackage. Tests follow the
baseline-then-mutate pattern: grab a fresh schema-valid package from
`baseline_package()`, break exactly ONE field, and assert the check catches it
(fail case) or leaves a clean package alone (pass case).

Chain-shape notes (changed from the vignette version):
  - Only SEGMENT 1 carries a start_keyframe; segments 2-3 inherit the previous
    clip's last frame (start_keyframe is None and the schema validator REQUIRES
    that). So any test that wants to plant a palette leak in a start_keyframe can
    only mutate shots[0] — there is no other start_keyframe to break.
  - mood_anchor is package-level now (one field), so the mood_anchor_identical
    check is gone (drift impossible by construction) — its two tests are deleted.
  - transition -> motion; organizing_principle -> device; the event-beat check is
    now device_requires_event_beat, conditional on the change-devices.
"""

import pytest

from src.evals.rubric_checks import (
    no_scale_comparison,
    no_quality_incantations,
    no_palette_in_keyframes,
    no_style_words_in_motion,
    device_requires_event_beat,
)
from tests.helpers.content_package import baseline_package

# PARKED behind the single-shot pivot (plan Task 7). The deterministic rubric
# checks + their baseline_package helper are built on the retired 3-shot
# chained-continuity schema (Device, inheritor shots with no start_keyframe), so
# they no longer construct under the single-shot ContentPackage. Kept on disk —
# not rewritten, not deleted — for a future render/vision judge; skipped so the
# suite stays green.
pytestmark = pytest.mark.skip(reason="writer rubric parked behind single-shot pivot (plan Task 7)")


def test_no_scale_comparison_fail():
    package = baseline_package()
    package.shots[2].motion = "the whale rises, as thick as a ship's mast"
    receipt = no_scale_comparison(package)

    assert receipt.passed is False


def test_no_scale_comparison_pass():
    package = baseline_package()
    package.shots[2].motion = "the whale rises slowly"
    receipt = no_scale_comparison(package)

    assert receipt.passed is True


def test_no_quality_incantations_fail():
    package = baseline_package()
    package.caption = "breathtaking 8K masterpiece"
    receipt = no_quality_incantations(package)

    assert receipt.passed is False
    assert "8k" in receipt.reason
    assert "masterpiece" in receipt.reason
    assert "breathtaking" in receipt.reason


def test_no_quality_incantations_pass():
    package = baseline_package()
    receipt = no_quality_incantations(package)

    assert receipt.passed is True


def test_no_palette_in_keyframes_start_fail():
    # Only segment 1 has a start_keyframe to leak palette into.
    package = baseline_package()
    package.shots[0].start_keyframe = "wide shot, deep teal and orange grade over the harbor"
    receipt = no_palette_in_keyframes(package)

    assert receipt.passed is False


def test_no_palette_in_keyframes_hex_fail():
    # TRAP MOVED: the old test mutated shots[1].start_keyframe — illegal now
    # (segment 2 is an inheritor, start_keyframe must be None). A hex leak can only
    # appear in a GENERATED frame: segment 1's start_keyframe or any end_keyframe.
    # Plant it in segment 3's end_keyframe to also prove the scan covers end frames.
    package = baseline_package()
    package.shots[2].end_keyframe = "the water settled under a #1a2b3c sky"
    receipt = no_palette_in_keyframes(package)

    assert receipt.passed is False
    assert "#1a2b3c" in receipt.reason


def test_no_palette_in_keyframes_scans_end_keyframes():
    # New (plan Step 2.1): an end_keyframe carrying palette vocab must fail — the
    # scan covers every GENERATED frame (opening still + end_keyframes), not just
    # the opening still.
    package = baseline_package()
    package.shots[2].end_keyframe = "tunnel walls closed, saturated teal palette glow"
    receipt = no_palette_in_keyframes(package)

    assert receipt.passed is False


def test_no_palette_in_keyframes_pass():
    package = baseline_package()
    receipt = no_palette_in_keyframes(package)

    assert receipt.passed is True


def test_no_style_words_in_motion_fail():
    package = baseline_package()
    package.shots[0].motion = "slow cinematic push-in"
    receipt = no_style_words_in_motion(package)

    assert receipt.passed is False
    assert "cinematic" in receipt.reason


def test_no_style_words_in_motion_pass():
    package = baseline_package()
    package.shots[0].motion = "slow push-in over 5s"
    receipt = no_style_words_in_motion(package)

    assert receipt.passed is True


def test_device_requires_event_beat_fail():
    # A change-device (transformation) with NO end_keyframe anywhere = the change
    # never lands on screen. Must fail. device_rationale updated to match the device
    # so the package is coherent.
    package = baseline_package()
    package.device = "transformation"
    package.device_rationale = "the premise is a becoming; the subject changes across the take"
    for shot in package.shots:
        shot.end_keyframe = None
    receipt = device_requires_event_beat(package)

    assert receipt.passed is False
    assert "end_keyframe" in receipt.reason


def test_device_requires_event_beat_pass():
    package = baseline_package()
    package.device = "transformation"
    package.device_rationale = "the premise is a becoming; the subject changes across the take"
    package.shots[1].end_keyframe = "the skin along the spine has split open"
    receipt = device_requires_event_beat(package)

    assert receipt.passed is True
