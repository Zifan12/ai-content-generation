"""Tests for the POV pipeline's Pydantic schemas (ticket 02).

Covers what ticket 02 owns: the extra="forbid" house convention, and the one
schema-level invariant POVBeat keeps (dialogue_line/speaker pairing). The
four cross-beat/whole-script structural rules (action count, beat-count
budget, dialogue-never-final-beat, duration in {10, 15}) are deliberately
NOT schema-enforced here — see schemas.py's module docstring — so no test
for them belongs in this file; they are ticket 04's.
"""

import pytest
from pydantic import ValidationError

from src.generation.pov.schemas import POVBeat, POVPitch, POVScript


def test_pov_pitch_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        POVPitch(
            who="a cave explorer",
            where="a crystal cavern",
            what_happens="finds a glowing shard",
            turn="the shard reacts to touch",
            money_shot="the shard flares and lights the whole cavern wall",
            unexpected_field="nope",  # type: ignore[call-arg]
        )


def test_pov_pitch_requires_money_shot() -> None:
    """money_shot has NO default (ticket 07) — an optional field silently
    reopens the capture gap: the operator's peak image staying unwritten until
    a paid watch is exactly the disease this field exists to close."""
    with pytest.raises(ValidationError):
        POVPitch(  # type: ignore[call-arg]
            who="a cave explorer",
            where="a crystal cavern",
            what_happens="finds a glowing shard",
            turn="the shard reacts to touch",
        )


def test_pov_beat_dialogue_requires_speaker() -> None:
    with pytest.raises(ValidationError):
        POVBeat(actions=["reaches for the shard"], dialogue_line="careful now")


def test_pov_beat_speaker_requires_dialogue() -> None:
    with pytest.raises(ValidationError):
        POVBeat(actions=["reaches for the shard"], speaker="the explorer")


def test_pov_beat_dialogue_and_speaker_together_is_valid() -> None:
    beat = POVBeat(
        actions=["reaches for the shard"],
        dialogue_line="careful now",
        speaker="the explorer",
    )
    assert beat.dialogue_line == "careful now"
    assert beat.speaker == "the explorer"


def test_pov_beat_silent_is_valid() -> None:
    beat = POVBeat(actions=["reaches for the shard"])
    assert beat.dialogue_line is None
    assert beat.speaker is None


def test_pov_script_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        POVScript(
            scene_setting="a crystal cavern",
            protagonist_role="explorer",
            protagonist_detail="with a headlamp",
            duration_seconds=10,
            camera_register="calm",
            beats=[POVBeat(actions=["walks forward"])],
            world_prose="Damp stone, faint light.",
            unexpected_field="nope",  # type: ignore[call-arg]
        )


def test_pov_script_requires_camera_register() -> None:
    """camera_register has NO default — a default would silently re-lock every
    story to one register, the first live run's failure (2026-07-17: calm-locked
    camera on an action story). The seat must choose per story."""
    with pytest.raises(ValidationError):
        POVScript(  # type: ignore[call-arg]
            scene_setting="a crystal cavern",
            protagonist_role="explorer",
            protagonist_detail="with a headlamp",
            duration_seconds=10,
            beats=[POVBeat(actions=["walks forward"])],
            world_prose="Damp stone, faint light.",
        )


def test_pov_script_rejects_unknown_camera_register() -> None:
    """Literal["calm", "action"] — an invalid register fails at parse (the
    cheapest layer that holds it), never reaching the compiler's clause lookup."""
    with pytest.raises(ValidationError):
        POVScript(
            scene_setting="a crystal cavern",
            protagonist_role="explorer",
            protagonist_detail="with a headlamp",
            duration_seconds=10,
            camera_register="frantic",  # type: ignore[arg-type]
            beats=[POVBeat(actions=["walks forward"])],
            world_prose="Damp stone, faint light.",
        )


def test_pov_beat_rejects_empty_actions() -> None:
    """An empty-actions beat IS the beat-free action line that renders in zero
    frames (BUG-031 class, PRD user story 5) — it must fail at parse, never
    reach the compiler or a paid render. Spec-axis review finding 2026-07-17."""
    with pytest.raises(ValidationError):
        POVBeat(actions=[])
