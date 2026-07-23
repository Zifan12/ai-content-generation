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

    def develop(self, pitch, ref_bound=(), declared_objects=()) -> POVScript:
        self.develop_calls += 1
        return _script()

    def repair(
        self, pitch, failed_script, violations, ref_bound=(), declared_objects=()
    ) -> POVScript:
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
    # Ticket 01: finals are native 1080p x1 (upscaled probes are never keepers).
    assert "--resolution 1080p" in outcome.released_final_command
    final_file = run_dir / "final_command.txt"
    assert final_file.exists()
    text = final_file.read_text(encoding="utf-8")
    assert outcome.released_final_command in text
    # The release carries its own operating notes: the 720p-native fallback for
    # a rejected 1080p+refs job, the second-take override route, and a verdict
    # reminder naming the ACTUAL final resolution (was hardcoded 720p).
    assert "720p" in text  # fallback guidance
    assert "force-final" in text  # second take = logged override
    assert "--resolution 1080p" in text.split("LOG IT")[1]


def test_run_sheet_withholds_final_until_verdict(run_dir: Path) -> None:
    """Probe gate at the source: the freshly-generated sheet carries the 480p
    command and the release instruction — never a 720p command."""
    sheet = (run_dir / "render_sheet.md").read_text(encoding="utf-8")

    assert "--resolution 480p" in sheet
    assert "--resolution 1080p" not in sheet
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

    assert "--resolution 1080p" in command
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
    """300cr cap (D2 grilling 2026-07-23): logged spend at/over the cap blocks
    release even for a passing take. Retro records carry REAL historical spend,
    so they count toward the tally (PRD story 23) while never parking."""
    # 3 retro 1080p fails (3 × 90cr) + this pass's own 90cr = 360cr ≥ 300.
    for _ in range(3):
        record_verdict(
            run_dir, result="fail", resolution="1080p", rules=rules,
            defects=["other"], retro=True,
        )
    outcome = record_verdict(run_dir, result="pass", resolution="1080p", rules=rules)

    assert outcome.released_final_command is None
    assert any("cap" in refusal for refusal in outcome.refusals)


def test_force_final_refuses_over_credit_cap(run_dir: Path, rules: RenderRules) -> None:
    """Review fix 2026-07-22: --force-final skips the PROBE, never the cap
    (PRD user story 18 vs 22) — 360cr of logged 1080p spend blocks a forced
    release at the 300cr cap."""
    for _ in range(4):
        record_verdict(
            run_dir, result="fail", resolution="1080p", rules=rules,
            defects=["other"], retro=True,
        )

    with pytest.raises(ValueError, match="cap"):
        force_release_final(run_dir, rules=rules)
    assert not (run_dir / "final_command.txt").exists()


def test_retro_fails_never_count_toward_the_park_threshold(
    run_dir: Path, rules: RenderRules
) -> None:
    """Review fix 2026-07-22: a seeded historical fail must not cost the story
    a live retake — 1 retro + 2 live fails is NOT a park (3 live would be)."""
    record_verdict(
        run_dir, result="fail", resolution="480p", rules=rules, defects=["other"], retro=True
    )
    record_verdict(run_dir, result="fail", resolution="480p", rules=rules, defects=["other"])
    outcome = record_verdict(
        run_dir, result="fail", resolution="480p", rules=rules, defects=["other"]
    )

    assert outcome.parked is False
    assert not (run_dir / "parked.json").exists()


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


# --- verdict truth: refs in the release + brakes (D2 ticket 05) --------------


def _ref_run(tmp_path: Path, rules: RenderRules, keeper_name: str = "keeper.png") -> Path:
    """A run with one promoted object ref (fixture PNG) through the real driver."""
    from src.generation.pov.schemas import POVWorldElement
    from tests.cli.test_pov import _PNG_HEADER

    refs = tmp_path / "refs"
    (refs / "hell_city").mkdir(parents=True, exist_ok=True)
    (refs / "hell_city" / keeper_name).write_bytes(_PNG_HEADER)
    script = _script().model_copy(
        update={
            "world_elements": [
                POVWorldElement(slug="hell_city", description="black gothic towers")
            ]
        }
    )
    return run_pov_pipeline(
        FakeObjectScriptWriter(script), rules, SAMPLE_IDEA,
        objects=["hell_city"],
        refs_root=refs,
        output_dir=tmp_path / "pov",
    )


class FakeObjectScriptWriter:
    def __init__(self, script: POVScript) -> None:
        self._script = script

    def develop(self, pitch, ref_bound=(), declared_objects=()) -> POVScript:
        return self._script

    def repair(
        self, pitch, failed_script, violations, ref_bound=(), declared_objects=()
    ) -> POVScript:
        raise AssertionError("fixture script is structurally valid; repair must not run")


def test_released_final_carries_the_validated_refs(tmp_path: Path, rules: RenderRules) -> None:
    """Staleness kill: the final command IS the probe command (same refs,
    absolute paths) at the final resolution — never a ref-less original."""
    run_dir = _ref_run(tmp_path, rules)

    outcome = record_verdict(run_dir, result="pass", resolution="480p", rules=rules)

    released = outcome.released_final_command
    assert released is not None
    keeper_abs = str((tmp_path / "refs" / "hell_city" / "keeper.png").resolve())
    assert f'--image "{keeper_abs}"' in released
    assert "--resolution 1080p" in released


def test_ref_swap_invalidates_a_prior_probe_pass(tmp_path: Path, rules: RenderRules) -> None:
    """Same prompt + same ref -> exempt; same prompt + RENAMED ref -> re-probe."""
    first = _ref_run(tmp_path, rules)
    record_verdict(first, result="pass", resolution="480p", rules=rules)

    same = _ref_run(tmp_path, rules)
    assert (same / "final_command.txt").exists()  # identical config: exempt

    (tmp_path / "refs" / "hell_city" / "keeper.png").unlink()
    swapped = _ref_run(tmp_path, rules, keeper_name="different_keeper.png")
    assert not (swapped / "final_command.txt").exists()  # new config: re-probe


def test_credit_cap_tally_includes_recorded_still_spend(
    run_dir: Path, rules: RenderRules
) -> None:
    """PRD story 23: the brake reads ALL recorded spend — still generation
    included. 300cr of still spend blocks the release a pass would earn."""
    from src.generation.pov.verdict import record_still_spend

    record_still_spend(run_dir, count=43, credits=301.0, note="hell_city x43")

    outcome = record_verdict(run_dir, result="pass", resolution="480p", rules=rules)

    assert outcome.released_final_command is None
    assert any("cap" in refusal for refusal in outcome.refusals)
