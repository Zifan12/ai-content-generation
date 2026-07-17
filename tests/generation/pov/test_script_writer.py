"""Tests for POVScriptWriter (src/generation/pov/script_writer.py, ticket 03).

Mirrors tests/generation/test_story_architect.py's FakeLLM idiom (ticket 03's
named exemplar). Unlike StoryArchitect there is no compose/code-copy step to
prove (script_writer.py's module docstring explains why: POVScript shares no
field with POVPitch) — these tests instead pin the two things that ARE this
seat's own contract: the structured-output call targets POVScript directly
with the max_tokens override, and the system prompt actually teaches the
story-shape rules the ticket names (beat budget, Setup->Turn->Button
collapsible button, emotion-as-physical-tells, dialogue-never-final-beat,
world-prose craft).
"""

from src.generation.pov.schemas import POVBeat, POVPitch, POVScript
from src.generation.pov.script_writer import (
    POV_SCRIPT_SYSTEM_PROMPT,
    POVScriptWriter,
)

SAMPLE_PITCH = POVPitch(
    who="a cave explorer",
    where="a crystal cavern deep underground",
    what_happens="the explorer finds a glowing shard and lifts it toward their eyes",
    turn="the shard's glow reveals the cavern is not empty after all",
)


def _script() -> POVScript:
    return POVScript(
        scene_setting="a damp crystal cavern",
        protagonist_role="explorer",
        protagonist_detail="with a headlamp, gloved hands occasionally visible",
        duration_seconds=10,
        beats=[
            POVBeat(actions=["the right hand reaches for the glowing shard"]),
            POVBeat(actions=["the hand lifts the shard toward the eyes"]),
        ],
        world_prose="Foreground rubble glistens, midground crystals pulse blue light.",
    )


class FakeLLM:
    def __init__(self, result: object) -> None:
        self._result = result

    def parse(self, prompt: str, response_model: type, **kwargs: object) -> object:
        self.prompt = prompt
        self.response_model = response_model
        self.system = kwargs.get("system")
        self.max_tokens = kwargs.get("max_tokens")
        return self._result


def test_develop_calls_llm_with_pov_script_response_model() -> None:
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    result = writer.develop(SAMPLE_PITCH)

    assert result is llm._result
    assert llm.response_model is POVScript
    assert llm.system == POV_SCRIPT_SYSTEM_PROMPT
    assert isinstance(llm.max_tokens, int) and llm.max_tokens > 0


def test_develop_injects_pitch_as_tagged_data() -> None:
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "<pitch>" in llm.prompt
    assert SAMPLE_PITCH.who in llm.prompt
    assert SAMPLE_PITCH.where in llm.prompt
    assert SAMPLE_PITCH.what_happens in llm.prompt
    assert SAMPLE_PITCH.turn in llm.prompt


def test_prompt_teaches_beat_budget_and_duration_choice() -> None:
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "4-6 beats" in llm.system
    assert "5-8 beats" in llm.system
    assert "duration_seconds" in llm.system


def test_prompt_teaches_setup_turn_button_collapsible() -> None:
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "SETUP -> TURN -> BUTTON" in llm.system
    assert "COLLAPSE" in llm.system


def test_prompt_teaches_emotion_as_physical_tells() -> None:
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "PHYSICAL TELLS" in llm.system
    assert "never write or imply an emotion word".upper() in llm.system.upper()


def test_prompt_teaches_dialogue_never_final_beat_and_plain_prose() -> None:
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "NEVER on the script's LAST beat" in llm.system
    assert "plain quoted prose" in llm.system


def test_prompt_teaches_world_prose_craft() -> None:
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "foreground" in llm.system.lower() and "midground" in llm.system.lower()
    assert "particulates" in llm.system.lower() or "dust" in llm.system.lower()


def test_prompt_teaches_beat_free_action_lines_fail() -> None:
    """The BUG-031/L9 lesson (beat-free lines render in zero frames) must
    survive relocation into this seat's prompt, uncompressed (StoryArchitect
    precedent: a compressed rule silently changes meaning)."""
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "ZERO FRAMES" in llm.system
