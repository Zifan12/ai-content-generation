"""Orchestration tests for scripts/pov.py run_pov_pipeline (ticket 03, seam 1).

Idea mode's tracer bullet: fake script seat, no network, no renders, no DB
(the POV pipeline has none — plain files only, PRD Implementation
Decisions). Per .scratch/pov-pipeline/PRD.md Testing Decisions ("idea mode
skips the pitcher entirely — fake records zero pitcher calls") and this
ticket's acceptance criteria: run directory created with pitch/script/prompt/
sheet artifacts, zero pitcher calls, pitch fields byte-identical between
operator input and sheet, and every named render-sheet element present.
"""

import json

from src.generation.pov.schemas import POVBeat, POVPitch, POVScript
from src.generation.render_adapters.rules import RenderRules
from scripts.pov import run_pov_pipeline

SAMPLE_IDEA = (
    "I dive into a sunken WWII wreck and find a still-ticking pocket watch "
    "wedged in the captain's cabin door."
)


def _script() -> POVScript:
    """A script whose composed body lands comfortably inside the compiler's
    60-100 word budget (mirrors test_compiler.py's tuned-in-range fixture)."""
    return POVScript(
        scene_setting="the flooded corridor of a sunken WWII wreck, shafts of murky light",
        protagonist_role="diver",
        protagonist_detail="with a dive light, gloved hands occasionally visible in frame",
        duration_seconds=10,
        beats=[
            POVBeat(
                actions=[
                    "the camera glides forward down the rust-streaked corridor",
                    "the right hand sweeps a drifting curtain of silt aside",
                ],
                audio_events=["muffled bubbling breath", "metal creaking distantly"],
            ),
            POVBeat(
                actions=[
                    "the hand reaches toward the cabin door",
                    "fingers close around a small ticking pocket watch wedged in the hinge",
                ],
                audio_events=["a faint mechanical ticking"],
            ),
        ],
        world_prose=(
            "Foreground silt drifts in the dive light's beam, midground rusted pipes hang "
            "loose from the ceiling, and background darkness swallows the corridor's far end."
        ),
    )


class FakeScriptWriter:
    def __init__(self, result: POVScript) -> None:
        self._result = result
        self.pitches: list[POVPitch] = []

    def develop(self, pitch: POVPitch) -> POVScript:
        self.pitches.append(pitch)
        return self._result


class FakePitcher:
    """A call-counting fake proving idea mode never touches the pitcher seam."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def pitch(self, topic: str) -> list[POVPitch]:
        self.calls.append(topic)
        return []


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
