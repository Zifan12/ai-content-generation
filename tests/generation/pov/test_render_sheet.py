"""Tests for the POV render sheet builder (src/generation/pov/render_sheet.py, ticket 03).

Seam-2-style pure-function tests (mirrors test_compiler.py): no LLM, no file
I/O. Asserts every element the ticket names must be in the sheet: verbatim
prompt, CLI command, cost line, mandatory-ladder wording, the four named
watch-checklist failure modes, the location-still escalation lever, and the
picked pitch's own fields byte-identical (code-copy proof — PRD user story
22 / this ticket's acceptance criteria).
"""

import pytest

from src.generation.pov.compiler import compile_pov_prompt
from src.generation.pov.render_sheet import build_render_sheet
from src.generation.pov.schemas import POVBeat, POVPitch, POVScript
from src.generation.render_adapters.rules import RenderRules

SAMPLE_PITCH = POVPitch(
    who="a cave explorer",
    where="a crystal cavern deep underground",
    what_happens="the explorer finds a glowing shard and lifts it toward their eyes",
    turn="the shard's glow reveals the cavern is not empty after all",
    money_shot="the raised shard lights the cavern and hundreds of eyes open at once",
)


def _script() -> POVScript:
    """A script whose composed body lands comfortably inside 60-100 words
    (mirrors test_compiler.py's tuned-in-range fixture)."""
    return POVScript(
        scene_setting="a damp mossy cave tunnel opening into a wide crystal cavern",
        protagonist_role="explorer",
        protagonist_detail=(
            "with a headlamp, gloved hands occasionally visible at the bottom of frame"
        ),
        duration_seconds=10,
        camera_register="calm",
        beats=[
            POVBeat(
                actions=[
                    "the camera walks forward through the narrow rock tunnel",
                    "the right hand braces against the cold wet wall",
                ],
                audio_events=["heavy breathing", "boots on wet stone"],
            ),
            POVBeat(
                actions=[
                    "the explorer pauses at the chamber threshold",
                    "then pans slowly across a field of glowing crystals",
                ],
                audio_events=["a low echoing drip"],
            ),
        ],
        world_prose=(
            "Foreground rubble glistens with damp moss, midground crystal spires pulse a "
            "faint steady blue light, and background darkness swallows the tunnel's far curve."
        ),
    )


@pytest.fixture(scope="module")
def rules() -> RenderRules:
    return RenderRules()


def test_sheet_contains_verbatim_prompt_cli_and_cost(rules: RenderRules) -> None:
    script = _script()
    compiled = compile_pov_prompt(script, rules)

    sheet = build_render_sheet(SAMPLE_PITCH, script, compiled, rules)

    assert compiled.prompt_text in sheet
    assert compiled.cli_command in sheet
    assert compiled.cost_line in sheet


def test_sheet_contains_mandatory_ladder_wording(rules: RenderRules) -> None:
    """Ticket 01 (D2): the POV lane carries its OWN ladder (probe -> watch ->
    native 1080p x1; upscaler = draft salvage), not the scene lane's x2-3
    wording — the blur lesson 2026-07-22."""
    script = _script()
    compiled = compile_pov_prompt(script, rules)

    sheet = build_render_sheet(SAMPLE_PITCH, script, compiled, rules)

    assert "MANDATORY" in sheet
    assert rules.pov_verdict()["ladder"] in sheet
    ladder = rules.pov_verdict()["ladder"]
    assert "1080p" in ladder
    assert "upscal" in ladder.lower()  # upscaler explicitly demoted


def test_sheet_contains_pov_watch_checklist_failure_modes(rules: RenderRules) -> None:
    script = _script()
    compiled = compile_pov_prompt(script, rules)

    sheet = build_render_sheet(SAMPLE_PITCH, script, compiled, rules)

    assert "ANGLE SWITCH" in sheet
    assert "BODY LEAK" in sheet
    assert "BEAT TELEPORT" in sheet
    assert "TEXT LEAK" in sheet


def test_sheet_prints_money_shot_and_checks_it_first(rules: RenderRules) -> None:
    """Ticket 07: the pitch's money_shot appears verbatim (gate-2 checks the
    operator's imagination against the plan) and MONEY SHOT LANDS is the FIRST
    watch-checklist item — the one question that fails the video on its own."""
    script = _script()
    compiled = compile_pov_prompt(script, rules)

    sheet = build_render_sheet(SAMPLE_PITCH, script, compiled, rules)

    assert SAMPLE_PITCH.money_shot in sheet
    assert "MONEY SHOT LANDS" in sheet
    assert sheet.index("MONEY SHOT LANDS") < sheet.index("ANGLE SWITCH")


def test_sheet_contains_location_still_escalation_lever(rules: RenderRules) -> None:
    script = _script()
    compiled = compile_pov_prompt(script, rules)

    sheet = build_render_sheet(SAMPLE_PITCH, script, compiled, rules)

    assert "escalation lever" in sheet.lower()
    assert "eye vantage" in sheet.lower() or "EYE VANTAGE" in sheet


def test_sheet_states_the_camera_register(rules: RenderRules) -> None:
    """The register is a taste-relevant knob the operator reviews at the sheet
    gate (first-live-run fix 2026-07-17) — it must be visible, not buried in
    script.json."""
    script = _script()
    compiled = compile_pov_prompt(script, rules)

    sheet = build_render_sheet(SAMPLE_PITCH, script, compiled, rules)

    assert "calm camera register" in sheet


def test_pitch_fields_byte_identical_in_sheet(rules: RenderRules) -> None:
    """Code-copy proof: the pitch's own fields survive verbatim, never
    re-derived from the script's authored prose."""
    script = _script()
    compiled = compile_pov_prompt(script, rules)

    sheet = build_render_sheet(SAMPLE_PITCH, script, compiled, rules)

    assert SAMPLE_PITCH.who in sheet
    assert SAMPLE_PITCH.where in sheet
    assert SAMPLE_PITCH.what_happens in sheet
    assert SAMPLE_PITCH.turn in sheet
