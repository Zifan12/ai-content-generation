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

import re
from pathlib import Path

import pytest

from src.generation.pov.asset_check import ResolvedCharacter
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
    assert clauses["continuous_take_constraint"]["text"] in compiled.prompt_text
    assert clauses["constraints_block"]["text"] in compiled.prompt_text
    assert clauses["style_register"][script.camera_register]["text"] in compiled.prompt_text
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


@pytest.mark.parametrize("register", ["calm", "action"])
def test_style_clause_present_per_register_and_before_audio(
    rules: RenderRules, register: str
) -> None:
    """BUG-033 regression: both probes carry a Style: sentence the original
    grammar transcription missed — the styleless kaiju render watched as 'not
    realistic or cinematic'. Every compiled prompt must carry its register's
    style clause verbatim, positioned before the Audio sentence (probe order)."""
    clauses = rules.pov_grammar()["skeleton_clauses"]
    compiled = compile_pov_prompt(_script(camera_register=register), rules)

    style_text = clauses["style_register"][register]["text"]
    assert style_text in compiled.prompt_text
    assert compiled.prompt_text.index(style_text) < compiled.prompt_text.index("Audio:")


def test_continuous_take_guard_present_after_anti_drift(rules: RenderRules) -> None:
    """Angle-switch regression (2026-07-17 kaiju run): take_480p.mp4 watched a
    mid-clip ANGLE SWITCH with anti_drift_constraint alone in the prompt; doc
    15:385's second guard ('This is one continuous take. No multiple camera
    angles.') then held POV in 3 consecutive watched takes. Every compiled
    prompt must carry BOTH camera guards, continuous-take directly in
    anti-drift's wake (the hand-edited passing takes' order)."""
    clauses = rules.pov_grammar()["skeleton_clauses"]
    compiled = compile_pov_prompt(_script(), rules)

    guard = clauses["continuous_take_constraint"]["text"]
    anti_drift = clauses["anti_drift_constraint"]["text"]
    assert guard in compiled.prompt_text
    assert compiled.prompt_text.index(anti_drift) < compiled.prompt_text.index(guard)
    assert compiled.prompt_text.index(guard) < compiled.prompt_text.index("Style:")


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


def test_filter_risk_action_words_are_substituted(rules: RenderRules) -> None:
    """Ticket 08: doc-19 §3 filter-risk action vocabulary (fight/battle/destroy,
    kill/brutal/attack, punch/slash, blood) must never reach a paid render bare —
    each word is substituted with its corpus phrase, word-boundary and
    case-insensitive, same mechanics as the glow/glimmer pass. The scene lane
    declares this table (seedance_2_0.dialect.sensitive_words) but the POV
    compiler never applied it — the verified gap RESEARCH-slice2.md §1 names."""
    replace_table = rules.pov_grammar()["kill_list"]["sensitive_actions"]["replace"]
    # Banned words spread across EVERY script-authored field type the ticket
    # names: actions, dialogue, audio, and the protagonist/scene/world prose.
    script = _script(
        protagonist_detail="with brutal gauntlets, gloved hands visible at frame bottom",
        scene_setting="a battle-scarred rooftop over a dim city block",
        world_prose=(
            "Foreground slash marks score the concrete, midground antennas lean "
            "sideways, background towers fade into haze."
        ),
        beats=[
            POVBeat(
                actions=[
                    "the gloved hands Attack the tower with a heavy punch",
                    "the fist smashes through to destroy the antenna",
                ],
                audio_events=["a distant fight rumbling", "no blood anywhere"],
            ),
            POVBeat(
                actions=["the arms recoil from the kill"],
                audio_events=["metal groan"],
                dialogue_line="stand down before this turns brutal",
                speaker="the radio voice",
            ),
        ],
    )
    compiled = compile_pov_prompt(script, rules)
    lowered = compiled.prompt_text.lower()

    banned_present = ["attack", "punch", "destroy", "fight", "blood", "kill", "brutal", "battle", "slash"]
    for banned in banned_present:
        assert banned in replace_table, f"config missing sensitive_actions row {banned!r}"
        assert not re.search(rf"\b{banned}\b", lowered), f"{banned!r} survived compilation"
    assert replace_table["attack"].lower() in lowered
    assert replace_table["punch"].lower() in lowered


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
    """Sized off the CONFIGURED cap, not a literal — the caps are live config
    (loosened to 150/220 as the 2026-07-22 BUG-040 experiment; revert pending
    an operator adherence verdict), and this test asserts the over-cap
    behavior, not the cap's value."""
    cap = rules.pov_grammar()["world_prose_craft"]["body_word_target"]["at_10s"]["max_words"]
    filler = " ".join(["word"] * (cap + 10))
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


def test_action_and_audio_items_with_trailing_periods_join_cleanly(rules: RenderRules) -> None:
    """A roll that authors actions/audio as full sentences ('...steel.') must not
    compose 'steel.;', 'glass.,', or a '..' ending — the kaiju beam rerun
    (2026-07-17) put all three on a sheet. Joiners own the punctuation."""
    script = _script(
        beats=[
            POVBeat(
                actions=["The hand smashes through glass and steel.", "The hand yanks back."],
                audio_events=["Crashing glass.", "Shredding wires."],
            ),
            POVBeat(
                actions=["Jet contrails curl toward camera."],
                audio_events=["Jet engines screaming closer."],
            ),
        ],
    )
    compiled = compile_pov_prompt(script, rules)

    assert ".;" not in compiled.prompt_text
    assert ".," not in compiled.prompt_text
    assert ".." not in compiled.prompt_text
    assert "steel; The hand yanks back" in compiled.prompt_text


def test_scene_setting_with_trailing_period_does_not_double_up(rules: RenderRules) -> None:
    """A scene_setting already ending in '.' must not compose 'Scene: ...x..' —
    the double-period defect the first kaiju rerun (2026-07-17) put on a sheet."""
    script = _script(scene_setting="a waist-high Tokyo intersection, dollhouse buildings.")
    compiled = compile_pov_prompt(script, rules)

    assert "dollhouse buildings." in compiled.prompt_text
    assert ".." not in compiled.prompt_text


def test_world_sentence_is_punctuated_before_anti_drift(rules: RenderRules) -> None:
    """Same run-on class, the other splice point: world_prose with no
    trailing punctuation must not run into the anti_drift_constraint clause."""
    filler = " ".join(["word"] * 8)
    script = _script(world_prose=f"Foreground rubble glistens with damp {filler} moss")
    compiled = compile_pov_prompt(script, rules)

    clauses = rules.pov_grammar()["skeleton_clauses"]
    anti_drift = clauses["anti_drift_constraint"]["text"]
    assert f"moss. {anti_drift}" in compiled.prompt_text


def test_cli_command_carries_image_flags_in_ref_order(rules: RenderRules) -> None:
    """Ticket 10/11: reference paths become repeated --image flags on the
    copy-paste CLI command, in upload order — the same order the binding
    clause numbers imageN by, so order is a contract, not cosmetics."""
    bound = [
        ResolvedCharacter(
            slug="hero", role="protagonist",
            ref_paths=["refs/hero/a_arm.png", "refs/hero/b_glove.png"],
        )
    ]
    compiled = compile_pov_prompt(_script(), rules, bound_characters=bound)

    # Paths are emitted ABSOLUTE (ticket 05: shell cwd drifts between the
    # operator's copy-paste calls) — resolve the fixtures the same way.
    a_arm = str(Path("refs/hero/a_arm.png").resolve())
    b_glove = str(Path("refs/hero/b_glove.png").resolve())
    first = compiled.cli_command.index(f'--image "{a_arm}"')
    second = compiled.cli_command.index(f'--image "{b_glove}"')
    assert first < second
    assert compiled.ref_paths == [a_arm, b_glove]


def test_cli_command_without_refs_has_no_image_flag(rules: RenderRules) -> None:
    compiled = compile_pov_prompt(_script(), rules)
    assert "--image" not in compiled.cli_command


def test_protagonist_binding_clause_frozen_wording_and_position(rules: RenderRules) -> None:
    """Ticket 11: the probe-frozen binding clause (ip_probe roll 1b, user-watch
    PASS 2026-07-19) compiles verbatim from config — role substituted, imageN
    list matching upload order — positioned directly after the Subject sentence
    (the roll-1 byte pattern)."""
    bound = [
        ResolvedCharacter(
            slug="silverhero", role="protagonist",
            ref_paths=["refs/silverhero/a.png", "refs/silverhero/b.png"],
        )
    ]
    script = _script()  # protagonist_role = "explorer"
    compiled = compile_pov_prompt(script, rules, bound_characters=bound)

    expected = (
        "The explorer's arms and hands are those of the character shown in image1, image2."
    )
    assert expected in compiled.prompt_text
    assert compiled.prompt_text.index("Subject:") < compiled.prompt_text.index(expected)
    assert compiled.prompt_text.index(expected) < compiled.prompt_text.index("Action, in order:")


def test_multi_character_binding_numbers_continue_across_characters(
    rules: RenderRules,
) -> None:
    """imageN numbering runs continuously across characters in upload order:
    protagonist's refs first (image1..2), then the in_frame character's
    (image3..4) using the scene-lane visible-character form."""
    bound = [
        ResolvedCharacter(
            slug="silverhero", role="protagonist",
            ref_paths=["refs/silverhero/a.png", "refs/silverhero/b.png"],
        ),
        ResolvedCharacter(
            slug="storm_foe", role="in_frame",
            ref_paths=["refs/storm_foe/mask.png", "refs/storm_foe/body.png"],
        ),
    ]
    compiled = compile_pov_prompt(_script(), rules, bound_characters=bound)

    assert "shown in image1, image2." in compiled.prompt_text
    assert "storm foe is the character shown in image3, image4." in compiled.prompt_text


def test_zero_characters_compiles_byte_identical_to_slice_one(rules: RenderRules) -> None:
    """No declared characters -> prompt text byte-identical to the pre-slice-②
    compiler output (ticket 11 acceptance: zero-character runs unchanged)."""
    script = _script()
    assert (
        compile_pov_prompt(script, rules).prompt_text
        == compile_pov_prompt(script, rules, bound_characters=()).prompt_text
    )


@pytest.mark.parametrize("duration", [10, 15])
def test_cost_line_matches_measured_rate(rules: RenderRules, duration: int) -> None:
    compiled = compile_pov_prompt(_script(duration_seconds=duration), rules)
    rate = rules.model(rules.scene_model())["limits"]["cost_estimate_credits"]["per_second_480p"]
    expected_cost = duration * rate
    assert str(expected_cost) in compiled.cost_line
    assert "480p" in compiled.cost_line


# --- object bindings (D2 ticket 03) ------------------------------------------


def test_object_binding_sentence_and_image_numbering_after_characters(
    rules: RenderRules,
) -> None:
    """D2: a bound object compiles to ONE positional binding sentence (config
    ip_binding.object, probe-C evidence) with imageN continuing after the
    character refs, and its ref path rides the CLI --image flags."""
    bound = [
        ResolvedCharacter(
            slug="silverhero", role="protagonist",
            ref_paths=["refs/silverhero/a.png", "refs/silverhero/b.png"],
        ),
        ResolvedCharacter(
            slug="hell_city", role="object", ref_paths=["refs/hell_city/keeper.png"],
        ),
    ]
    compiled = compile_pov_prompt(_script(), rules, bound_characters=bound)

    assert "The hell city is shown in image3." in compiled.prompt_text
    keeper = str(Path("refs/hell_city/keeper.png").resolve())
    assert f'--image "{keeper}"' in compiled.cli_command


def test_world_element_descriptions_never_reach_the_prompt(rules: RenderRules) -> None:
    """The grill-Q1 field-drop contract: a bound object's seat-authored
    description feeds still generation only — the compiled prompt carries the
    binding sentence, never the description prose (two descriptions of one
    thing fighting on screen = pitch-51 camera-hijack class)."""
    from src.generation.pov.schemas import POVWorldElement

    script = _script()
    script = script.model_copy(
        update={
            "world_elements": [
                POVWorldElement(
                    slug="hell_city",
                    description="dense black gothic towers with streets of molten lava",
                )
            ]
        }
    )
    bound = [
        ResolvedCharacter(
            slug="hell_city", role="object", ref_paths=["refs/hell_city/keeper.png"],
        )
    ]
    compiled = compile_pov_prompt(script, rules, bound_characters=bound)

    assert "gothic towers" not in compiled.prompt_text
    assert "The hell city is shown in image1." in compiled.prompt_text


def test_world_elements_do_not_count_toward_the_word_budget(rules: RenderRules) -> None:
    """Descriptions are still-generation data, not authored render body — a
    script exactly at the cap must not be pushed over by world_elements."""
    from src.generation.pov.compiler import count_body_words
    from src.generation.pov.schemas import POVWorldElement

    script = _script()
    with_elements = script.model_copy(
        update={
            "world_elements": [
                POVWorldElement(slug="hell_city", description="a " * 500)
            ]
        }
    )
    assert count_body_words(with_elements) == count_body_words(script)
