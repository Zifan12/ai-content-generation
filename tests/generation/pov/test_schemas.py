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
            unexpected_field="nope",  # type: ignore[call-arg]
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
            beats=[POVBeat(actions=["walks forward"])],
            world_prose="Damp stone, faint light.",
            unexpected_field="nope",  # type: ignore[call-arg]
        )
