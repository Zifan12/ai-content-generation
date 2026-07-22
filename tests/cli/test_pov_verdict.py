"""Seam-1 driver tests for the slice-③ verdict flow (record_verdict + probe gate).

.scratch/pov-slice3/PRD.md Testing Decisions, seam 1 (prior art:
tests/cli/test_pov.py — fake script seat, temp dirs, plain files, no DB, no
network). Each test builds a real run directory via ``run_pov_pipeline`` with
the fake seat, then drives the verdict flow against it:

- FAIL verdict → defect counted, final command withheld
- PASS verdict at 480p → final (720p) command released
- recurrence gate → nothing drafted at one occurrence, a draft notice at two
- identical prompt hash with a prior probe PASS → probe auto-exempt at run time
- ``force_final`` → final released, bypass recorded
- 150cr cap crossed / second failed retake → refusal + parked forensics
- retro-tagged seeds count toward recurrence
"""

import json
from pathlib import Path

import pytest

from src.generation.pov.schemas import POVBeat, POVScript
from src.generation.pov.verdict import force_release_final, record_verdict
from src.generation.render_adapters.rules import RenderRules
from scripts.pov import run_pov_pipeline

SAMPLE_IDEA = (
    "I dive into a sunken WWII wreck and find a still-ticking pocket watch "
    "wedged in the captain's cabin door."
)


def _script() -> POVScript:
    """In-budget 10s/4-beat script (mirrors tests/cli/test_pov.py's fixture)."""
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
    def __init__(self) -> None:
        self.develop_calls = 0

    def develop(self, pitch, ref_bound=()) -> POVScript:
        self.develop_calls += 1
        return _script()

    def repair(self, pitch, failed_script, violations, ref_bound=()) -> POVScript:
        raise AssertionError("fixture script is structurally valid; repair must not run")


@pytest.fixture(scope="module")
def rules() -> RenderRules:
    return RenderRules()


@pytest.fixture()
def run_dir(tmp_path: Path, rules: RenderRules) -> Path:
    """A real pipeline run under a temp output dir (lane log lands beside it)."""
    return run_pov_pipeline(
        FakeScriptWriter(), rules, SAMPLE_IDEA, output_dir=tmp_path / "pov"
    )


def _log_path(run_dir: Path) -> Path:
    return run_dir.parent / "verdicts.jsonl"


def _log_records(run_dir: Path) -> list[dict]:
    text = _log_path(run_dir).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# --- fail path ---------------------------------------------------------------


def test_fail_verdict_logs_defect_and_withholds_final(run_dir: Path, rules: RenderRules) -> None:
    outcome = record_verdict(
        run_dir,
        result="fail",
        resolution="480p",
        rules=rules,
        defects=["angle_switch"],
        note="cut to third person at the door",
    )

    assert outcome.released_final_command is None
    assert not (run_dir / "final_command.txt").exists()
    records = _log_records(run_dir)
    assert len(records) == 1
    assert records[0]["result"] == "fail"
    assert records[0]["defects"] == ["angle_switch"]
    assert records[0]["run"] == run_dir.name


def test_fail_tag_defaults_from_taxonomy_and_note_is_kept(
    run_dir: Path, rules: RenderRules
) -> None:
    record_verdict(
        run_dir,
        result="fail",
        resolution="480p",
        rules=rules,
        defects=["money_shot_missed"],
        note="peak never lands",
    )

    record = _log_records(run_dir)[0]
    # money_shot_missed's taxonomy default_tag is taste; operator gave no override.
    assert record["tag"] == "taste"
    assert record["note"] == "peak never lands"


def test_unknown_defect_slug_is_rejected_loudly(run_dir: Path, rules: RenderRules) -> None:
    with pytest.raises(ValueError, match="not in the defect taxonomy"):
        record_verdict(
            run_dir,
            result="fail",
            resolution="480p",
            rules=rules,
            defects=["explosion_went_sideways"],
        )
    assert not _log_path(run_dir).exists()


# --- pass path / probe gate --------------------------------------------------


def test_probe_pass_releases_final_command(run_dir: Path, rules: RenderRules) -> None:
    outcome = record_verdict(run_dir, result="pass", resolution="480p", rules=rules)

    assert outcome.released_final_command is not None
    assert "--resolution 720p" in outcome.released_final_command
    final_file = run_dir / "final_command.txt"
    assert final_file.exists()
    assert outcome.released_final_command in final_file.read_text(encoding="utf-8")


def test_run_sheet_withholds_final_until_verdict(run_dir: Path) -> None:
    """Probe gate at the source: the freshly-generated sheet carries the 480p
    command and the release instruction — never a 720p command."""
    sheet = (run_dir / "render_sheet.md").read_text(encoding="utf-8")

    assert "--resolution 480p" in sheet
    assert "--resolution 720p" not in sheet
    assert "verdict" in sheet  # tells the operator how the final is released


def test_prior_pass_on_same_prompt_hash_auto_exempts_probe(
    tmp_path: Path, rules: RenderRules
) -> None:
    """Same idea + same fake script → identical compiled prompt → second run
    starts with its final command already released (grill Q2c)."""
    out = tmp_path / "pov"
    first = run_pov_pipeline(FakeScriptWriter(), rules, SAMPLE_IDEA, output_dir=out)
    record_verdict(first, result="pass", resolution="480p", rules=rules)

    second = run_pov_pipeline(FakeScriptWriter(), rules, SAMPLE_IDEA, output_dir=out)

    assert (second / "final_command.txt").exists()
    sheet = (second / "render_sheet.md").read_text(encoding="utf-8")
    assert "probe already passed" in sheet.lower()


def test_force_final_releases_and_records_bypass(run_dir: Path, rules: RenderRules) -> None:
    command = force_release_final(run_dir, rules=rules)

    assert "--resolution 720p" in command
    assert (run_dir / "final_command.txt").exists()
    records = _log_records(run_dir)
    assert records[0]["event"] == "force_final"


# --- recurrence gate ---------------------------------------------------------


def test_recurrence_gate_stays_silent_at_one_occurrence(
    run_dir: Path, rules: RenderRules
) -> None:
    outcome = record_verdict(
        run_dir, result="fail", resolution="480p", rules=rules, defects=["wrong_pose"]
    )

    assert outcome.recurrence_notices == []


def test_recurrence_gate_drafts_notice_at_two_independent_runs(
    tmp_path: Path, rules: RenderRules
) -> None:
    out = tmp_path / "pov"
    first = run_pov_pipeline(FakeScriptWriter(), rules, SAMPLE_IDEA, output_dir=out)
    second = run_pov_pipeline(FakeScriptWriter(), rules, "a different story idea", output_dir=out)

    record_verdict(first, result="fail", resolution="480p", rules=rules, defects=["wrong_pose"])
    outcome = record_verdict(
        second, result="fail", resolution="480p", rules=rules, defects=["wrong_pose"]
    )

    assert len(outcome.recurrence_notices) == 1
    assert "wrong_pose" in outcome.recurrence_notices[0]
    assert "2" in outcome.recurrence_notices[0]


def test_repeat_fails_on_the_same_run_do_not_fake_recurrence(
    run_dir: Path, rules: RenderRules
) -> None:
    """Recurrence means independent renders (Deming: distinct samples), not the
    same take re-logged."""
    record_verdict(run_dir, result="fail", resolution="480p", rules=rules, defects=["wrong_pose"])
    outcome = record_verdict(
        run_dir, result="fail", resolution="480p", rules=rules, defects=["wrong_pose"]
    )

    assert outcome.recurrence_notices == []


def test_retro_seeds_count_toward_recurrence(tmp_path: Path, rules: RenderRules) -> None:
    """PRD story 14: lessons already paid for count — a retro-tagged seed plus
    one live fail = recurrence."""
    out = tmp_path / "pov"
    seeded = run_pov_pipeline(FakeScriptWriter(), rules, SAMPLE_IDEA, output_dir=out)
    record_verdict(
        seeded, result="fail", resolution="480p", rules=rules,
        defects=["wrong_scale"], retro=True,
    )
    live = run_pov_pipeline(FakeScriptWriter(), rules, "another story", output_dir=out)

    outcome = record_verdict(
        live, result="fail", resolution="480p", rules=rules, defects=["wrong_scale"]
    )

    assert len(outcome.recurrence_notices) == 1
    assert _log_records(seeded)[0]["retro"] is True


# --- spending brakes ---------------------------------------------------------


def test_second_failed_retake_parks_story_with_forensics(
    run_dir: Path, rules: RenderRules
) -> None:
    """D7 ladder: first fail + 2 failed retakes → parked, forensics written,
    no further commands released."""
    record_verdict(run_dir, result="fail", resolution="480p", rules=rules, defects=["other"])
    record_verdict(run_dir, result="fail", resolution="480p", rules=rules, defects=["other"])
    outcome = record_verdict(
        run_dir, result="fail", resolution="480p", rules=rules, defects=["other"]
    )

    assert outcome.parked is True
    forensics = json.loads((run_dir / "parked.json").read_text(encoding="utf-8"))
    assert len(forensics["verdicts"]) == 3
    assert forensics["credits_spent"] > 0
    # A parked story releases nothing, even on force.
    with pytest.raises(ValueError, match="parked"):
        force_release_final(run_dir, rules=rules)


def test_credit_cap_refuses_further_release(run_dir: Path, rules: RenderRules) -> None:
    """150cr cap (grill Q1): logged spend at/over the cap blocks release even
    for a passing take."""
    # Two watched 1080p takes at 10s = 2 × 90cr = 180cr ≥ the 150cr cap.
    record_verdict(run_dir, result="fail", resolution="1080p", rules=rules, defects=["other"])
    outcome = record_verdict(run_dir, result="pass", resolution="1080p", rules=rules)

    assert outcome.released_final_command is None
    assert any("cap" in refusal for refusal in outcome.refusals)


def test_verdict_requires_defect_on_fail(run_dir: Path, rules: RenderRules) -> None:
    """A fail with no named defect is uncountable — the log's whole point."""
    with pytest.raises(ValueError, match="defect"):
        record_verdict(run_dir, result="fail", resolution="480p", rules=rules)


def test_prediction_artifacts_written_at_run_time(run_dir: Path) -> None:
    """Deming Study step: the theory is on disk before the watch."""
    prediction = (run_dir / "prediction.txt").read_text(encoding="utf-8")
    sheet = (run_dir / "render_sheet.md").read_text(encoding="utf-8")

    assert "angle_switch" in prediction
    assert "UNGUARDED" in prediction
    assert "Prediction" in sheet
