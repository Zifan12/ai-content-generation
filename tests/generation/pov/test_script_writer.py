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
    POV_SCRIPT_REPAIR_SYSTEM_PROMPT,
    POV_SCRIPT_SYSTEM_PROMPT,
    POVScriptWriter,
)

SAMPLE_PITCH = POVPitch(
    who="a cave explorer",
    where="a crystal cavern deep underground",
    what_happens="the explorer finds a glowing shard and lifts it toward their eyes",
    turn="the shard's glow reveals the cavern is not empty after all",
    money_shot="the raised shard lights the cavern and hundreds of eyes open at once",
)


def _script() -> POVScript:
    return POVScript(
        scene_setting="a damp crystal cavern",
        protagonist_role="explorer",
        protagonist_detail="with a headlamp, gloved hands occasionally visible",
        duration_seconds=10,
        camera_register="calm",
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


def test_prompt_teaches_camera_register_choice_and_action_15s_default() -> None:
    """First-live-run fixes (2026-07-17): the seat must choose camera_register
    by story energy (calm-locked camera was the measured failure) and action
    stories default to 15s (every proven action POV example is 15s)."""
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "camera_register" in llm.system
    assert '"calm"' in llm.system and '"action"' in llm.system
    assert "default to 15" in llm.system


def test_prompt_teaches_money_shot_climax_binding() -> None:
    """Ticket 07 (grill Q3-B): the climax delivers the pitch's money_shot —
    final beat default, penultimate legal under a button that never
    out-scales it; placeholder note (idea mode) means infer the peak."""
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "DELIVER THE MONEY SHOT AT THE CLIMAX" in llm.system
    assert "FINAL beat by default" in llm.system
    assert "never out-scale" in llm.system
    assert "placeholder note" in llm.system


def test_prompt_teaches_escalation_and_event_beats() -> None:
    """First-live-run fixes (2026-07-17): beats must escalate scale (final beat
    = largest image) and change the SCENE, not just the hand — micro-step
    chains were the measured 'not interesting' failure."""
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "ESCALATE SCALE BEAT TO BEAT" in llm.system
    assert "LARGEST image" in llm.system
    assert "EVENT BEATS, NOT MICRO-STEPS" in llm.system
    assert "CHANGE THE SCENE" in llm.system


def test_prompt_teaches_entrance_staging_choice() -> None:
    """Staging-candidate promotion (2026-07-18, kaiju run watch): 'helicopter
    buzzes close' with no origin popped into existence at point-blank; the
    re-staged approach beat rendered cause->effect on the passing watch. The
    rule is a forced CHOICE (anticipation or surprise), never a blanket
    everything-must-enter mandate — in-scene objects and camera-turn reveals
    are exempt by its own text."""
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "STAGE EVERY ENTRANCE" in llm.system
    assert "ANTICIPATION OR SURPRISE, NEVER UNCHOSEN" in llm.system
    assert "things that ARRIVE" in llm.system


def test_prompt_teaches_scale_anchoring_for_nonhuman_protagonists() -> None:
    """Scale-class promotion (BUG-034, 2026-07-19, /root-cause gate): 2nd watched
    instance of wrong-scale rendering (giant read person-sized; earlier: dollhouse
    toy textures). Disease: no scale-anchoring contract existed, and the word-economy
    rule taught cutting the anchors first. The rule is judgment-shaped: relative cues
    sizing the PROTAGONIST against a normal world — never shrinking the world — and
    scale anchors are exempted from first-cut word trimming."""
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "ANCHOR NON-HUMAN SCALE WITH RELATIVE CUES" in llm.system
    assert "never anchor by shrinking the world" in llm.system.lower()
    assert "LAST words cut" in llm.system


def test_prompt_teaches_sustained_effect_end_beat() -> None:
    """Sustained-effect promotion (BUG-035, 2026-07-19): 2nd watched instance of an
    unauthored effect hold (ip_probe roll 1b: beam never ends, still firing after the
    kaiju fell; take_480p_roll2: hands deform mid-hold while the beam keeps firing).
    The rule is judgment-shaped: a released continuous effect gets an authored countable
    END action, and the sustaining limbs never linger unauthored until it lands."""
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "END EVERY SUSTAINED EFFECT" in llm.system
    assert "the stream cuts off, both arms lower" in llm.system
    assert "improvises the hold" in llm.system


def test_prompt_teaches_beat_free_action_lines_fail() -> None:
    """The BUG-031/L9 lesson (beat-free lines render in zero frames) must
    survive relocation into this seat's prompt, uncompressed (StoryArchitect
    precedent: a compressed rule silently changes meaning)."""
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)

    writer.develop(SAMPLE_PITCH)

    assert "ZERO FRAMES" in llm.system


# --- repair() (ticket 04) ----------------------------------------------------
# Mirrors tests/generation/test_story_architect.py's
# test_repair_returns_composed_script_and_carries_failure_notes — the named
# exemplar's own repair coverage. Everything that exercises repair() via
# craft_enforcement.develop_valid_script (tests/generation/pov/
# test_craft_enforcement.py) uses a FakeScriptWriter, so the real prompt
# assembly (system/response_model/max_tokens, and the violation +
# failed_script actually reaching the LLM prompt) is only proven here.


def test_repair_calls_llm_with_pov_script_response_model_and_repair_system_prompt() -> None:
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)
    failed = _script()

    result = writer.repair(SAMPLE_PITCH, failed, ["duration_seconds must be 10 or 15, got 12"])

    assert result is llm._result
    assert llm.response_model is POVScript
    assert llm.system == POV_SCRIPT_REPAIR_SYSTEM_PROMPT
    assert llm.system != POV_SCRIPT_SYSTEM_PROMPT
    assert isinstance(llm.max_tokens, int) and llm.max_tokens > 0


def test_repair_injects_pitch_failed_script_and_violations_into_the_prompt() -> None:
    llm = FakeLLM(_script())
    writer = POVScriptWriter(llm=llm)
    failed = _script()
    violation = "the last beat carries a dialogue_line; dialogue must never land on the final beat"

    writer.repair(SAMPLE_PITCH, failed, [violation])

    assert "<pitch>" in llm.prompt
    assert SAMPLE_PITCH.who in llm.prompt
    assert "<failed_script>" in llm.prompt
    assert failed.model_dump_json(indent=2) in llm.prompt
    assert "<violations>" in llm.prompt
    assert violation in llm.prompt
