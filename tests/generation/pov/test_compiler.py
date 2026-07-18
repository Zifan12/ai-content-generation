"""Tests for the POV prompt compiler (ticket 02, seam 2 — pure function).

Per .scratch/pov-pipeline/PRD.md Testing Decisions: seam 2 asserts fixed
skeleton clauses present verbatim; kill-list words absent from output
regardless of input prose; no bracketed timestamps; word budget respected;
CLI command matches chosen params; cost line matches the measured rate
table. All assertions are external-behavior (compiled output text/fields),
never implementation-detail — no private helper is imported.

Fixed-clause and kill-list assertions read ``RenderRules().pov_grammar()``
directly (the REAL committed yaml) rather than hardcoding clause/word
strings in the test, so a future edit to the config can't silently drift out
of sync with what this test actually proves.
"""

import pytest

from src.generation.pov.compiler import POVWordBudgetError, compile_pov_prompt
from src.generation.pov.schemas import CompiledPOVPrompt, POVBeat, POVScript
from src.generation.render_adapters.rules import RenderRules


def _script(
    *,
    duration_seconds: int = 10,
    camera_register: str = "calm",
    protagonist_detail: str = (
        "with a headlamp, gloved hands occasionally visible at the bottom of frame"
    ),
    scene_setting: str = "a damp mossy cave tunnel opening into a wide crystal cavern",
    world_prose: str = (
        "Foreground rubble glistens with damp moss, midground crystal spires pulse a "
        "faint steady blue light, and background darkness swallows the tunnel's far curve."
    ),
    beats: list[POVBeat] | None = None,
) -> POVScript:
    """A script whose composed body lands comfortably inside 60-100 words."""
    return POVScript(
        scene_setting=scene_setting,
        protagonist_role="explorer",
        protagonist_detail=protagonist_detail,
        duration_seconds=duration_seconds,
        camera_register=camera_register,
        beats=beats
        or [
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
        world_prose=world_prose,
    )


@pytest.fixture(scope="module")
def rules() -> RenderRules:
    return RenderRules()


def test_returns_compiled_pov_prompt(rules: RenderRules) -> None:
    compiled = compile_pov_prompt(_script(), rules)
    assert isinstance(compiled, CompiledPOVPrompt)


def test_fixed_clauses_present_byte_verbatim(rules: RenderRules) -> None:
    """Every skeleton clause survives in the output — the [PROTAGONIST]-templated
    clauses with only the bracket token substituted, the other three untouched."""
    clauses = rules.pov_grammar()["skeleton_clauses"]
    script = _script()
    compiled = compile_pov_prompt(script, rules)

    role = script.protagonist_role
    assert (
        clauses["camera_as_eyes"][script.camera_register]["text"].replace("[PROTAGONIST]", role)
        in compiled.prompt_text
    )
    assert (
        clauses["unseen_protagonist"]["text"].replace("[PROTAGONIST]", role)
        in compiled.prompt_text
    )
    # Non-templated clauses: exact config string, untouched.
    assert clauses["anti_drift_constraint"]["text"] in compiled.prompt_text
    assert clauses["constraints_block"]["text"] in compiled.prompt_text
    # hands_visible must NOT exist as a skeleton clause — the slice-1 verifier
    # killed it as probe-unvalidated boilerplate; hands live inline in the
    # script-authored protagonist_detail (pov_grammar.protagonist_detail_craft).
    assert "hands_visible" not in clauses


@pytest.mark.parametrize("register", ["calm", "action"])
def test_camera_register_selects_its_variant_and_excludes_the_other(
    rules: RenderRules, register: str
) -> None:
    """The script's camera_register picks WHICH camera_as_eyes variant opens the
    prompt (first live run 2026-07-17: calm-locked camera on an action story) —
    the chosen variant's text present verbatim, the other's distinguishing
    language absent."""
    clauses = rules.pov_grammar()["skeleton_clauses"]
    script = _script(camera_register=register)
    compiled = compile_pov_prompt(script, rules)

    chosen = clauses["camera_as_eyes"][register]["text"].replace(
        "[PROTAGONIST]", script.protagonist_role
    )
    assert chosen in compiled.prompt_text
    if register == "calm":
        assert "hyper-chaotic" not in compiled.prompt_text.lower()
    else:
        assert "slight natural shake" not in compiled.prompt_text.lower()


def test_kill_list_words_never_survive(rules: RenderRules) -> None:
    kill_list = rules.pov_grammar()["kill_list"]
    script = _script(
        protagonist_detail=(
            "with a stunning headlamp, gloved hands occasionally visible at the bottom of frame"
        ),
        world_prose=(
            "Foreground rubble shows a faint glimmer of damp moss, midground crystal spires "
            "glow with faint blue light, cinematic and background darkness swallows the "
            "tunnel's far curve, an ultra-detailed masterpiece of natural stone."
        ),
        beats=[
            POVBeat(
                actions=[
                    "the camera walks forward through the breathtaking narrow rock tunnel",
                    "the right hand braces against the cold wet wall",
                ],
                audio_events=["heavy breathing", "boots on wet stone"],
            ),
            POVBeat(
                actions=[
                    "the explorer pauses at the chamber threshold",
                    "then pans slowly across a field of pulsing crystals",
                ],
                audio_events=["a low echoing drip"],
            ),
        ],
    )
    compiled = compile_pov_prompt(script, rules)
    lowered = compiled.prompt_text.lower()

    for word in kill_list["dead_intensifiers"]["words"]:
        assert word.lower() not in lowered, f"kill-list word {word!r} survived compilation"

    cinematic = kill_list["cinematic_without_specifics"]["word"]
    assert cinematic.lower() not in lowered

    for banned in kill_list["glow_glimmer"]["replace"]:
        assert banned.lower() not in lowered, f"{banned!r} survived compilation"


def test_no_bracketed_timestamps_survive_under_any_input(rules: RenderRules) -> None:
    """A bracketed timestamp injected into LLM-authored prose must never reach output —
    the compiler's whole purpose is to keep this documented render-killer off a paid
    render, regardless of what the script stage's prose happens to contain."""
    script = _script(
        beats=[
            POVBeat(
                actions=[
                    "[0-3s] the right hand braces against the cold wet wall",
                    "then reaches for the [4-6s] glowing shard",
                ],
                audio_events=["heavy breathing"],
            ),
        ],
    )
    compiled = compile_pov_prompt(script, rules)
    assert "[" not in compiled.prompt_text
    assert "]" not in compiled.prompt_text


def test_word_budget_too_short_raises(rules: RenderRules) -> None:
    script = _script(
        protagonist_detail="quiet.",
        scene_setting="a cave.",
        world_prose="Dark.",
        beats=[POVBeat(actions=["walks forward"], audio_events=[])],
    )
    with pytest.raises(POVWordBudgetError):
        compile_pov_prompt(script, rules)


def test_word_budget_too_long_raises(rules: RenderRules) -> None:
    filler = " ".join(["word"] * 40)
    script = _script(
        world_prose=(
            "Foreground rubble glistens with damp moss, midground crystal spires pulse a "
            f"faint steady blue light, and background darkness swallows the {filler} curve."
        ),
    )
    with pytest.raises(POVWordBudgetError):
        compile_pov_prompt(script, rules)


def test_word_budget_within_range_does_not_raise(rules: RenderRules) -> None:
    compile_pov_prompt(_script(), rules)  # must not raise


def test_empty_audio_events_does_not_produce_malformed_audio_line(rules: RenderRules) -> None:
    """A script whose beats author no audio_events must not compose 'Audio: , no music.' —
    a leading-comma artifact reaching a paid render."""
    filler = " ".join(["word"] * 20)
    script = _script(
        world_prose=(
            "Foreground rubble glistens with damp moss, midground crystal spires pulse a "
            f"faint steady blue light, and background darkness swallows the {filler} curve."
        ),
        beats=[
            POVBeat(actions=["the camera walks forward through the narrow rock tunnel"]),
            POVBeat(actions=["the explorer pauses at the chamber threshold"]),
        ],
    )
    compiled = compile_pov_prompt(script, rules)
    assert "Audio: , " not in compiled.prompt_text
    assert "Audio: no music." in compiled.prompt_text


@pytest.mark.parametrize("duration", [10, 15])
def test_cli_command_matches_chosen_duration(rules: RenderRules, duration: int) -> None:
    compiled = compile_pov_prompt(_script(duration_seconds=duration), rules)
    assert rules.scene_model() in compiled.cli_command
    assert "9:16" in compiled.cli_command
    assert f"--duration {duration}" in compiled.cli_command
    assert "480p" in compiled.cli_command


def test_subject_sentence_is_punctuated_before_action(rules: RenderRules) -> None:
    """A protagonist_detail with no trailing punctuation must not run on into
    the next sentence — a real defect class found eyeballing a produced render
    sheet (ticket 03). The compiler must insert a period, not rely on the
    script's own prose ending cleanly."""
    script = _script(protagonist_detail="with a headlamp, gloved hands occasionally visible")
    compiled = compile_pov_prompt(script, rules)

    assert "visible. Action, in order:" in compiled.prompt_text
    assert "visible Action, in order:" not in compiled.prompt_text


def test_world_sentence_is_punctuated_before_anti_drift(rules: RenderRules) -> None:
    """Same run-on class, the other splice point: world_prose with no
    trailing punctuation must not run into the anti_drift_constraint clause."""
    filler = " ".join(["word"] * 8)
    script = _script(world_prose=f"Foreground rubble glistens with damp {filler} moss")
    compiled = compile_pov_prompt(script, rules)

    clauses = rules.pov_grammar()["skeleton_clauses"]
    anti_drift = clauses["anti_drift_constraint"]["text"]
    assert f"moss. {anti_drift}" in compiled.prompt_text


@pytest.mark.parametrize("duration", [10, 15])
def test_cost_line_matches_measured_rate(rules: RenderRules, duration: int) -> None:
    compiled = compile_pov_prompt(_script(duration_seconds=duration), rules)
    rate = rules.model(rules.scene_model())["limits"]["cost_estimate_credits"]["per_second_480p"]
    expected_cost = duration * rate
    assert str(expected_cost) in compiled.cost_line
    assert "480p" in compiled.cost_line
