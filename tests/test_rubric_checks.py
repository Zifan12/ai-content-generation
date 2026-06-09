"""
Tests for the deterministic ("code-check") rubric criteria (Task 1).

Each criterion is a pure function over a ContentPackage. Tests follow the
baseline-then-mutate pattern: grab a fresh schema-valid package from
`baseline_package()`, break exactly ONE field, and assert the check catches it
(fail case) or leaves a clean package alone (pass case).
"""

from src.schemas.generation import ContentPackage, Shot
from src.evals.rubric_checks import (
    mood_anchor_identical,
    no_scale_comparison,
    no_quality_incantations,
    no_palette_in_start_keyframe,
    no_style_words_in_transition,
    escalating_wrongness_has_event_beat,
)

def baseline_package() -> ContentPackage:
    """
    Return a fresh, schema-valid ContentPackage that passes every v0 criterion.

    A new object is built on every call so a test that mutates one field cannot
    leak into the next test. The defaults are deliberately "clean": all three
    shots share a byte-identical mood_anchor, no shot carries scale-comparison or
    quality-incantation words, start_keyframes hold no palette vocabulary,
    transitions are motion-only, and the organizing_principle is "sustained_mood"
    (so the escalating_wrongness event-beat criterion does not apply). Mutate one
    field per test to drive a single criterion to fail.
    """
    mood = "cold teal light, photoreal, faintly uncanny"
    shots = [
        Shot(
            start_keyframe="wide shot, harbor at dawn, fishing boats moored",
            transition="slow push in over 5s",
            mood_anchor=mood,
            beat_position="opening",
        ),
        Shot(
            start_keyframe="medium shot, gulls circling a lone mast",
            transition="gentle drift left",
            mood_anchor=mood,
            beat_position="middle",
        ),
        Shot(
            start_keyframe="close shot, water lapping the dock pilings",
            transition="hold, faint shimmer on the water",
            mood_anchor=mood,
            beat_position="closing",
        ),
    ]
    return ContentPackage(
        shots=shots,
        organizing_principle="sustained_mood",
        principle_rationale="One quiet harbor, one mood, three framings of the same calm.",
        onscreen_text=[],
        caption="dawn at the harbor",
        hashtags=["#surreal", "#harbor"],
    )


def test_mood_anchor_identical_fail():

    package = baseline_package()
    package.shots[2].mood_anchor = "B"
    receipt = mood_anchor_identical(package)

    assert receipt.passed is False

def test_mood_anchor_identical_oass():

    package = baseline_package()
    receipt = mood_anchor_identical(package)

    assert receipt.passed is True

def test_no_scale_comparison_fail():
    package = baseline_package()
    package.shots[2].start_keyframe = "the whale is as thick as"
    receipt = no_scale_comparison(package)

    assert receipt.passed is False

def test_no_scale_comparison_pass():
    package = baseline_package()
    package.shots[2].start_keyframe = "the whale"
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


def test_no_palette_in_start_keyframe_fail():
    package = baseline_package()
    package.shots[0].start_keyframe = "wide shot, deep teal and orange grade over the harbor"
    receipt = no_palette_in_start_keyframe(package)

    assert receipt.passed is False
    assert "1" in receipt.reason


def test_no_palette_in_start_keyframe_hex_fail():
    package = baseline_package()
    package.shots[1].start_keyframe = "gulls over a #1a2b3c sky"
    receipt = no_palette_in_start_keyframe(package)

    assert receipt.passed is False
    assert "#1a2b3c" in receipt.reason


def test_no_palette_in_start_keyframe_pass():
    package = baseline_package()
    receipt = no_palette_in_start_keyframe(package)

    assert receipt.passed is True


def test_no_style_words_in_transition_fail():
    package = baseline_package()
    package.shots[0].transition = "slow cinematic push-in"
    receipt = no_style_words_in_transition(package)

    assert receipt.passed is False
    assert "cinematic" in receipt.reason


def test_no_style_words_in_transition_pass():
    package = baseline_package()
    package.shots[0].transition = "slow push-in over 5s"
    receipt = no_style_words_in_transition(package)

    assert receipt.passed is True


def test_escalating_wrongness_has_event_beat_fail():
    package = baseline_package()
    for shot in package.shots:
        shot.end_keyframe = None
    receipt = escalating_wrongness_has_event_beat(package)

    assert receipt.passed is False


def test_escalating_wrongness_has_event_beat_pass():
    package = baseline_package()
    package.shots[1].end_keyframe = "the tentacle now grips the hull"
    receipt = escalating_wrongness_has_event_beat(package)

    assert receipt.passed is True
