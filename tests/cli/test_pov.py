"""Orchestration tests for scripts/pov.py run_pov_pipeline (tickets 03 + 05, seam 1).

Idea mode's tracer bullet: fake script seat, no network, no renders, no DB
(the POV pipeline has none — plain files only, PRD Implementation
Decisions). Per .scratch/pov-pipeline/PRD.md Testing Decisions ("idea mode
skips the pitcher entirely — fake records zero pitcher calls") and this
ticket's acceptance criteria: run directory created with pitch/script/prompt/
sheet artifacts, zero pitcher calls, pitch fields byte-identical between
operator input and sheet, and every named render-sheet element present.

Ticket 04 wires ``craft_enforcement.develop_valid_script`` into
``run_pov_pipeline`` in place of a bare ``script_writer.develop`` call
(module docstring, scripts/pov.py) — ``_script()`` below now carries 4 beats
so it satisfies the 10s beat-count budget (4-6, pov_grammar.beat_budget) as
well as the compiler's own word-budget check, and ``FakeScriptWriter`` grew a
``repair`` method so it can stand in for the real seat on the wiring seam.
Ticket 04's own violation/repair/hard-fail matrix is unit-tested directly
against ``craft_enforcement.develop_valid_script``
(tests/generation/pov/test_craft_enforcement.py); the one test added here
(``test_a_structurally_invalid_script_is_repaired_before_writing``) only
proves the CLI driver actually routes through that enforcement rather than
bypassing it.

Ticket 05 adds topic mode: a fake pitcher seat produces a slate, a fake
``choice_provider`` picks by number, and the picked pitch flows through the
SAME downstream as idea mode. ``FakePitcher`` now returns a real
``POVPitchSlate`` (not an empty list) so it can stand in for
``src.generation.pov.pitcher.POVPitcher`` on this wiring seam.
"""

import json

import pytest

from src.generation.pov.craft_enforcement import POVStructuralViolationError
from src.generation.pov.schemas import POVBeat, POVPitch, POVPitchSlate, POVScript
from src.generation.render_adapters.rules import RenderRules
from scripts.pov import run_pov_pipeline

SAMPLE_IDEA = (
    "I dive into a sunken WWII wreck and find a still-ticking pocket watch "
    "wedged in the captain's cabin door."
)


def _script() -> POVScript:
    """A script whose composed body lands comfortably inside the compiler's
    60-100 word budget (mirrors test_compiler.py's tuned-in-range fixture)
    AND satisfies the 10s beat-count budget (4-6 beats, pov_grammar.beat_budget)."""
    return POVScript(
        scene_setting="the flooded corridor of a sunken WWII wreck, shafts of murky light",
        protagonist_role="diver",
        protagonist_detail="with a dive light, gloved hands occasionally visible in frame",
        duration_seconds=10,
        camera_register="calm",
        beats=[
            POVBeat(
                actions=["the camera glides forward down the rust-streaked corridor"],
                audio_events=["muffled bubbling breath"],
            ),
            POVBeat(
                actions=["the right hand sweeps a drifting curtain of silt aside"],
                audio_events=["metal creaking distantly"],
            ),
            POVBeat(
                actions=["the hand reaches toward the cabin door"],
                audio_events=["a faint mechanical ticking"],
            ),
            POVBeat(
                actions=["fingers close around a small ticking pocket watch wedged in the hinge"],
                audio_events=["the ticking grows louder"],
            ),
        ],
        world_prose=(
            "Foreground silt drifts in the dive light's beam, midground rusted pipes hang "
            "loose from the ceiling, and background darkness swallows the corridor's far end."
        ),
    )


class FakeScriptWriter:
    def __init__(self, result: POVScript, repaired: POVScript | None = None) -> None:
        self._result = result
        self._repaired = repaired
        self.pitches: list[POVPitch] = []
        self.repair_calls: list[tuple[POVPitch, POVScript, list[str]]] = []

    def develop(self, pitch: POVPitch) -> POVScript:
        self.pitches.append(pitch)
        return self._result

    def repair(
        self, pitch: POVPitch, failed_script: POVScript, violations: list[str]
    ) -> POVScript:
        self.repair_calls.append((pitch, failed_script, violations))
        assert self._repaired is not None, "test did not configure a repaired script"
        return self._repaired


def _slate() -> POVPitchSlate:
    """A 3-pitch slate of CLEARLY DISTINCT entries (different who/where/what_happens)
    so a pick-index test can only pass if the correct entry — not merely A
    valid-looking entry — reached the artifacts (advisor review: near-identical
    fixture pitches would let an off-by-one index bug pass silently)."""
    return POVPitchSlate(
        pitches=[
            POVPitch(
                who="a cave explorer",
                where="a flooded limestone cave",
                what_happens="the explorer's headlamp catches something moving in the water",
                turn="it is their own reflection, delayed by half a second",
                money_shot="the reflection keeps moving after the explorer freezes",
            ),
            POVPitch(
                who="a deep-sea diver",
                where="the flooded corridor of a sunken WWII wreck",
                what_happens="the diver sweeps silt aside and reaches for a door handle",
                turn="a still-ticking pocket watch is wedged in the hinge",
                money_shot="the watch face glows through the silt cloud, still ticking",
            ),
            POVPitch(
                who="a night-shift mechanic",
                where="an abandoned observatory dome",
                what_happens="the mechanic climbs a ladder toward a jammed telescope mount",
                turn="the dome slit is already open, aimed at something on the ground",
                money_shot="through the open slit, a floodlit shape on the lawn looks up",
            ),
        ]
    )


class FakePitcher:
    """A call-counting fake standing in for src.generation.pov.pitcher.POVPitcher.

    Idea mode uses this only to prove it is NEVER called (zero calls
    recorded); topic mode uses it to prove the driver actually calls
    ``pitch(topic)`` and routes its slate onward.
    """

    def __init__(self, slate: POVPitchSlate | None = None) -> None:
        self._slate = slate if slate is not None else _slate()
        self.calls: list[str] = []

    def pitch(self, topic: str) -> POVPitchSlate:
        self.calls.append(topic)
        return self._slate


def _rules() -> RenderRules:
    return RenderRules()


def test_idea_mode_writes_all_four_artifacts(tmp_path) -> None:
    writer = FakeScriptWriter(_script())

    run_dir = run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, output_dir=tmp_path)

    assert (run_dir / "pitch.json").exists()
    assert (run_dir / "script.json").exists()
    assert (run_dir / "prompt.txt").exists()
    assert (run_dir / "render_sheet.md").exists()


def test_idea_mode_never_calls_the_pitcher(tmp_path) -> None:
    writer = FakeScriptWriter(_script())
    pitcher = FakePitcher()

    run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, pitcher=pitcher, output_dir=tmp_path)

    assert pitcher.calls == []


def test_idea_mode_calls_script_writer_exactly_once(tmp_path) -> None:
    writer = FakeScriptWriter(_script())

    run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, output_dir=tmp_path)

    assert len(writer.pitches) == 1


def test_pitch_fields_byte_identical_operator_input_to_artifacts(tmp_path) -> None:
    """Code-copy proof: the operator's idea text reaches pitch.json and the
    render sheet completely unmodified — no LLM ever saw or paraphrased it
    on the way to either artifact."""
    writer = FakeScriptWriter(_script())

    run_dir = run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, output_dir=tmp_path)

    pitch_data = json.loads((run_dir / "pitch.json").read_text(encoding="utf-8"))
    assert pitch_data["what_happens"] == SAMPLE_IDEA

    sheet_text = (run_dir / "render_sheet.md").read_text(encoding="utf-8")
    assert SAMPLE_IDEA in sheet_text


def test_render_sheet_contains_prompt_cli_cost_ladder_checklist_lever(tmp_path) -> None:
    writer = FakeScriptWriter(_script())

    run_dir = run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, output_dir=tmp_path)

    sheet_text = (run_dir / "render_sheet.md").read_text(encoding="utf-8")
    prompt_text = (run_dir / "prompt.txt").read_text(encoding="utf-8")

    assert prompt_text in sheet_text
    assert "higgsfield generate create" in sheet_text
    assert "cr" in sheet_text  # cost line
    assert "MANDATORY" in sheet_text
    assert "ANGLE SWITCH" in sheet_text
    assert "BODY LEAK" in sheet_text
    assert "BEAT TELEPORT" in sheet_text
    assert "TEXT LEAK" in sheet_text
    assert "escalation lever" in sheet_text.lower()


def test_two_runs_with_the_same_idea_do_not_collide(tmp_path) -> None:
    writer = FakeScriptWriter(_script())

    run_dir_1 = run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, output_dir=tmp_path)
    run_dir_2 = run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, output_dir=tmp_path)

    assert run_dir_1 != run_dir_2
    assert run_dir_1.exists() and run_dir_2.exists()


def test_driver_docstring_documents_live_smoke_command() -> None:
    import scripts.pov as pov_module

    assert "uv run python scripts/pov.py --idea" in pov_module.__doc__


def test_a_structurally_invalid_script_is_repaired_before_writing(tmp_path) -> None:
    """Proves the driver routes through craft_enforcement.develop_valid_script
    rather than a bare script_writer.develop call (ticket 04 wiring): a first
    draft with only 2 beats (below the 10s budget's 4-6 minimum) triggers
    exactly one repair call, and the REPAIRED script's beat count is what
    reaches the written artifacts."""
    violating = POVScript(
        scene_setting="a damp crystal cavern",
        protagonist_role="explorer",
        protagonist_detail="with a headlamp, gloved hands occasionally visible",
        duration_seconds=10,
        camera_register="calm",
        beats=[
            POVBeat(actions=["the hand reaches for the glowing shard"]),
            POVBeat(actions=["the hand lifts the shard toward the eyes"]),
        ],
        world_prose="Foreground rubble glistens, midground crystals pulse blue light.",
    )
    writer = FakeScriptWriter(violating, repaired=_script())

    run_dir = run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, output_dir=tmp_path)

    assert len(writer.repair_calls) == 1
    script_data = json.loads((run_dir / "script.json").read_text(encoding="utf-8"))
    assert len(script_data["beats"]) == len(_script().beats)


def test_unrepairable_script_raises_loud_and_writes_nothing(tmp_path) -> None:
    """A violation surviving the one bounded repair must hard-fail the driver
    (no silent pass-through into the compiler) and leave no run directory
    (or an empty one) behind — the wiring-level mirror of
    test_craft_enforcement.py's own unrepairable-output test."""
    violating = POVScript(
        scene_setting="a damp crystal cavern",
        protagonist_role="explorer",
        protagonist_detail="with a headlamp, gloved hands occasionally visible",
        duration_seconds=10,
        camera_register="calm",
        beats=[
            POVBeat(actions=["the hand reaches for the glowing shard"]),
            POVBeat(actions=["the hand lifts the shard toward the eyes"]),
        ],
        world_prose="Foreground rubble glistens, midground crystals pulse blue light.",
    )
    writer = FakeScriptWriter(violating, repaired=violating)  # repair returns the same violation

    with pytest.raises(POVStructuralViolationError):
        run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, output_dir=tmp_path)

    assert list(tmp_path.iterdir()) == []


# --- money-shot contract (ticket 07) ----------------------------------------


def test_idea_mode_money_shot_flag_flows_verbatim_to_artifacts(tmp_path) -> None:
    """Code-copy proof for --money-shot: the operator's stated peak image
    reaches pitch.json and the sheet byte-identical — no LLM saw it."""
    writer = FakeScriptWriter(_script())
    stated = "the beam erupts and the helicopter bursts into a fireball"

    run_dir = run_pov_pipeline(
        writer, _rules(), SAMPLE_IDEA, money_shot=stated, output_dir=tmp_path
    )

    pitch_data = json.loads((run_dir / "pitch.json").read_text(encoding="utf-8"))
    assert pitch_data["money_shot"] == stated
    assert stated in (run_dir / "render_sheet.md").read_text(encoding="utf-8")


def test_idea_mode_without_money_shot_gets_the_unset_placeholder(tmp_path) -> None:
    import scripts.pov as pov_module

    writer = FakeScriptWriter(_script())

    run_dir = run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, output_dir=tmp_path)

    pitch_data = json.loads((run_dir / "pitch.json").read_text(encoding="utf-8"))
    assert pitch_data["money_shot"] == pov_module._MONEY_SHOT_UNSET_NOTE


def test_topic_mode_rejects_money_shot_kwarg(tmp_path) -> None:
    """Topic-mode pitches carry their own money_shot from the pitcher —
    a CLI-level --money-shot with --topic must fail loud, not be dropped."""
    writer = FakeScriptWriter(_script())
    pitcher = FakePitcher()

    with pytest.raises(ValueError):
        run_pov_pipeline(
            writer, _rules(), pitcher=pitcher, topic="deep sea",
            choice_provider=lambda: "1", money_shot="a peak", output_dir=tmp_path,
        )


def test_cli_parser_accepts_money_shot_with_idea() -> None:
    import scripts.pov as pov_module

    parser = pov_module._build_parser()
    args = parser.parse_args(["--idea", "x", "--money-shot", "the fireball"])
    assert args.money_shot == "the fireball"


def test_slate_print_includes_the_money_line(capsys) -> None:
    import scripts.pov as pov_module

    pov_module._print_slate(_slate())

    out = capsys.readouterr().out
    assert "money:" in out
    for pitch in _slate().pitches:
        assert pitch.money_shot in out


# --- topic mode (ticket 05) --------------------------------------------------


def test_topic_mode_requires_pitcher_and_topic(tmp_path) -> None:
    writer = FakeScriptWriter(_script())

    with pytest.raises(ValueError):
        run_pov_pipeline(writer, _rules(), output_dir=tmp_path)  # neither idea nor topic

    with pytest.raises(ValueError):
        run_pov_pipeline(  # both idea and topic
            writer, _rules(), SAMPLE_IDEA, topic="deep sea", output_dir=tmp_path
        )

    with pytest.raises(ValueError):
        run_pov_pipeline(  # topic with no pitcher
            writer, _rules(), topic="deep sea", output_dir=tmp_path
        )


def test_topic_mode_calls_pitcher_with_the_topic(tmp_path) -> None:
    writer = FakeScriptWriter(_script())
    pitcher = FakePitcher()

    run_pov_pipeline(
        writer, _rules(), pitcher=pitcher, topic="deep sea",
        choice_provider=lambda: "1", output_dir=tmp_path,
    )

    assert pitcher.calls == ["deep sea"]


def test_topic_mode_pick_is_honored_and_code_copied_downstream(tmp_path) -> None:
    """The advisor-flagged discriminating test: 3 DISTINCT fixture pitches,
    pick "2" (1-based) must resolve to slate.pitches[1] specifically — proving
    the index map is right, not just "some" pitch reached the artifacts, and
    that the script writer developed the PICKED pitch, not a different one."""
    writer = FakeScriptWriter(_script())
    slate = _slate()
    pitcher = FakePitcher(slate)
    expected = slate.pitches[1]

    run_dir = run_pov_pipeline(
        writer, _rules(), pitcher=pitcher, topic="deep sea",
        choice_provider=lambda: "2", output_dir=tmp_path,
    )

    assert writer.pitches == [expected]

    pitch_data = json.loads((run_dir / "pitch.json").read_text(encoding="utf-8"))
    assert pitch_data["who"] == expected.who
    assert pitch_data["where"] == expected.where
    assert pitch_data["what_happens"] == expected.what_happens
    assert pitch_data["turn"] == expected.turn
    # And NOT the other two pitches' distinguishing content — guards against a
    # pass-through bug that always writes pitches[0] regardless of the pick.
    assert pitch_data["what_happens"] != slate.pitches[0].what_happens
    assert pitch_data["what_happens"] != slate.pitches[2].what_happens

    sheet_text = (run_dir / "render_sheet.md").read_text(encoding="utf-8")
    assert expected.what_happens in sheet_text


def test_topic_mode_persists_the_full_slate_including_unpicked_pitches(tmp_path) -> None:
    writer = FakeScriptWriter(_script())
    slate = _slate()
    pitcher = FakePitcher(slate)

    run_dir = run_pov_pipeline(
        writer, _rules(), pitcher=pitcher, topic="deep sea",
        choice_provider=lambda: "2", output_dir=tmp_path,
    )

    slate_data = json.loads((run_dir / "slate.json").read_text(encoding="utf-8"))
    assert len(slate_data["pitches"]) == 3
    for original, persisted in zip(slate.pitches, slate_data["pitches"], strict=True):
        assert persisted["what_happens"] == original.what_happens


def test_idea_mode_writes_no_slate_file(tmp_path) -> None:
    writer = FakeScriptWriter(_script())

    run_dir = run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, output_dir=tmp_path)

    assert not (run_dir / "slate.json").exists()


def test_topic_mode_invalid_pick_raises_loud(tmp_path) -> None:
    writer = FakeScriptWriter(_script())
    pitcher = FakePitcher()

    with pytest.raises(ValueError):
        run_pov_pipeline(
            writer, _rules(), pitcher=pitcher, topic="deep sea",
            choice_provider=lambda: "99", output_dir=tmp_path,
        )

    with pytest.raises(ValueError):
        run_pov_pipeline(
            writer, _rules(), pitcher=pitcher, topic="deep sea",
            choice_provider=lambda: "not a number", output_dir=tmp_path,
        )


# --- asset gate (ticket 10) ---------------------------------------------------


def _write_refs(refs_root, slug: str, names: list[str]) -> list:
    """Create refs/<slug>/ with the named files; returns the created paths."""
    char_dir = refs_root / slug
    char_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names:
        p = char_dir / name
        p.write_bytes(b"\x89PNG fake image bytes")
        paths.append(p)
    return paths


def test_missing_refs_dir_raises_request_sheet_before_any_llm_call(tmp_path) -> None:
    """The gate fails BEFORE any LLM spend: no script-writer call, no pitcher
    call, no run directory — just the role-specific request sheet."""
    from src.generation.pov.asset_check import POVAssetRequestNeeded

    writer = FakeScriptWriter(_script())
    pitcher = FakePitcher()
    out_dir = tmp_path / "out"

    with pytest.raises(POVAssetRequestNeeded) as exc_info:
        run_pov_pipeline(
            writer, _rules(), SAMPLE_IDEA,
            pitcher=pitcher,
            characters=["silverhero"],
            refs_root=tmp_path / "refs",
            output_dir=out_dir,
        )

    assert writer.pitches == []
    assert pitcher.calls == []
    assert not out_dir.exists() or list(out_dir.iterdir()) == []
    sheet = exc_info.value.sheet_text
    assert "silverhero" in sheet
    assert "forearms" in sheet  # protagonist-role crop instructions present
    assert "NO face/mask panel" in sheet  # the anti-summon warning, protagonist role


def test_valid_refs_proceed_and_cli_carries_image_flags_in_order(tmp_path) -> None:
    paths = _write_refs(tmp_path / "refs", "silverhero", ["b_glove.png", "a_arm.png"])

    writer = FakeScriptWriter(_script())
    run_dir = run_pov_pipeline(
        writer, _rules(), SAMPLE_IDEA,
        characters=["silverhero"],
        refs_root=tmp_path / "refs",
        output_dir=tmp_path / "out",
    )

    sheet_text = (run_dir / "render_sheet.md").read_text(encoding="utf-8")
    # filename-sorted within the character: a_arm before b_glove
    a_arm = next(p for p in paths if p.name == "a_arm.png")
    b_glove = next(p for p in paths if p.name == "b_glove.png")
    assert f'--image "{a_arm}"' in sheet_text
    assert f'--image "{b_glove}"' in sheet_text
    assert sheet_text.index(f'--image "{a_arm}"') < sheet_text.index(f'--image "{b_glove}"')
    assert "Reference assets" in sheet_text


def test_protagonist_refs_precede_in_frame_refs_regardless_of_declaration_order(
    tmp_path,
) -> None:
    """Upload order defines imageN for ticket 11's binding clause — protagonist
    characters' refs always come first, whatever order the flags were typed in."""
    _write_refs(tmp_path / "refs", "foe", ["mask.png", "body.png"])
    _write_refs(tmp_path / "refs", "hero", ["arm.png", "glove.png"])

    writer = FakeScriptWriter(_script())
    run_dir = run_pov_pipeline(
        writer, _rules(), SAMPLE_IDEA,
        characters=["foe:in_frame", "hero:protagonist"],
        refs_root=tmp_path / "refs",
        output_dir=tmp_path / "out",
    )

    sheet_text = (run_dir / "render_sheet.md").read_text(encoding="utf-8")
    assert sheet_text.index("arm.png") < sheet_text.index("mask.png")


def test_ref_count_out_of_bounds_raises_named_error(tmp_path) -> None:
    _write_refs(tmp_path / "refs", "silverhero", ["only_one.png"])

    writer = FakeScriptWriter(_script())
    with pytest.raises(ValueError, match="silverhero"):
        run_pov_pipeline(
            writer, _rules(), SAMPLE_IDEA,
            characters=["silverhero"],
            refs_root=tmp_path / "refs",
            output_dir=tmp_path / "out",
        )
    assert writer.pitches == []


def test_non_image_file_in_refs_dir_raises(tmp_path) -> None:
    refs_root = tmp_path / "refs"
    _write_refs(refs_root, "silverhero", ["a.png", "b.png"])
    (refs_root / "silverhero" / "notes.txt").write_text("not an image", encoding="utf-8")

    writer = FakeScriptWriter(_script())
    with pytest.raises(ValueError, match="notes.txt"):
        run_pov_pipeline(
            writer, _rules(), SAMPLE_IDEA,
            characters=["silverhero"],
            refs_root=refs_root,
            output_dir=tmp_path / "out",
        )


def test_unknown_role_raises_naming_allowed_roles(tmp_path) -> None:
    writer = FakeScriptWriter(_script())
    with pytest.raises(ValueError, match="in_frame"):
        run_pov_pipeline(
            writer, _rules(), SAMPLE_IDEA,
            characters=["silverhero:villain"],
            refs_root=tmp_path / "refs",
            output_dir=tmp_path / "out",
        )


def test_no_character_flag_keeps_slice_one_behavior_byte_identical(tmp_path) -> None:
    writer = FakeScriptWriter(_script())
    run_dir = run_pov_pipeline(writer, _rules(), SAMPLE_IDEA, output_dir=tmp_path)

    sheet_text = (run_dir / "render_sheet.md").read_text(encoding="utf-8")
    assert "--image" not in sheet_text
    assert "Reference assets" not in sheet_text


def test_cli_parser_accepts_repeated_character_flags() -> None:
    import scripts.pov as pov_module

    parser = pov_module._build_parser()
    args = parser.parse_args(
        ["--idea", "x", "--character", "silverhero", "--character", "foe:in_frame"]
    )
    assert args.character == ["silverhero", "foe:in_frame"]


def test_topic_and_idea_are_mutually_exclusive_on_the_cli() -> None:
    import scripts.pov as pov_module

    parser = pov_module._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--idea", "x", "--topic", "y"])


def test_topic_or_idea_is_required_on_the_cli() -> None:
    import scripts.pov as pov_module

    parser = pov_module._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
