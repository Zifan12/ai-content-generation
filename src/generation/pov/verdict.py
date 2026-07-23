"""POV verdict flow (slice ③) — watch verdicts in, released commands + lessons out.

.scratch/pov-slice3/PRD.md is the spec. This module is the deterministic core
of the first-try-success package:

- :func:`prompt_hash` — content key for the probe-exemption rule (grill Q2c:
  a prompt whose exact compiled text already has a probe PASS on record never
  re-probes).
- :func:`build_prediction_block` — the Deming "Study" fix (consult
  2026-07-22): the ruleset states its own expected on-screen outcomes BEFORE
  the operator watches, derived mechanically from the config taxonomy's
  guarded entries — a fail then reads as "rule was active and still failed"
  vs "nothing predicted this", instead of a bare tally.
- :func:`record_verdict` — the seam-1 orchestration: validates the defect
  slugs against the taxonomy, writes the run's verdict record + appends the
  lane-wide log, counts recurrence across DISTINCT runs (first sighting =
  data point, >=2 = draft-a-rule notice; rules are NEVER auto-written — the
  notice asks the operator to ratify), enforces the spending brakes (150cr
  per-story cap, 2-failed-retakes park), and — on a probe PASS — releases the
  final-resolution command.
- :func:`force_release_final` — grill Q2b: the deliberate probe skip. Releases
  the final but records the bypass as its own event type, so a failed
  skipped-probe render is attributable to the bypass, not the gate.

Everything is plain files (PRD: no DB): per-run artifacts live in the run
directory; the lane-wide log is ONE append-only JSONL beside the run
directories (``<output_dir>/verdicts.jsonl``) so recurrence counting reads a
single place.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from src.generation.pov.schemas import POVScript
from src.generation.render_adapters.rules import RenderRules

# "other" is always loggable (grill Q3: a brand-new failure mode must never
# block the log) but never counts toward recurrence — two "other"s are two
# UNKNOWN defects, not evidence of the same cause. Promotion into the taxonomy
# is a ratified config edit, mirroring the rule-row convention.
_OTHER = "other"

_LOG_NAME = "verdicts.jsonl"
_FINAL_COMMAND_FILE = "final_command.txt"
_PARKED_FILE = "parked.json"
_PREDICTION_FILE = "prediction.txt"


class POVVerdictRecord(BaseModel):
    """One logged event on the lane-wide verdict log (one JSONL line).

    ``event`` distinguishes a watched verdict from a deliberate probe bypass
    (``force_final``) — both share the record shape so the log stays one
    schema. ``retro`` marks seeded records reconstructed from documented
    watched verdicts (PRD user story 14): they count toward recurrence but
    stay distinguishable if we ever distrust them. ``credits`` is this
    event's OWN render spend (duration x measured rate; 0 for force_final,
    which spends nothing itself), so a story's total is a plain sum over its
    records.
    """

    model_config = ConfigDict(extra="forbid")

    event: Literal["verdict", "force_final"]
    run: str  # run directory name — the story/run identity in the log
    result: Literal["pass", "fail"] | None  # None for force_final events
    resolution: str | None  # the watched render's resolution; None for force_final
    duration_seconds: int
    prompt_hash: str
    defects: list[str] = []
    tag: Literal["objective", "taste"] | None = None
    note: str | None = None
    credits: float = 0.0
    retro: bool = False
    timestamp: str = ""


class VerdictOutcome(BaseModel):
    """What :func:`record_verdict` did, for the CLI to print and tests to assert.

    ``released_final_command`` is set only when this verdict released the
    final-resolution command. ``recurrence_notices`` carries one line per
    defect class that JUST crossed the recurrence gate (>=2 distinct runs) —
    the operator's cue to ratify a rule row; nothing is auto-written.
    ``refusals`` names every brake that blocked a release (credit cap,
    parked story). ``parked`` is True when THIS verdict crossed the
    retake limit and wrote the forensics file.
    """

    model_config = ConfigDict(extra="forbid")

    record: POVVerdictRecord
    released_final_command: str | None = None
    recurrence_notices: list[str] = []
    refusals: list[str] = []
    parked: bool = False


def prompt_hash(prompt_text: str) -> str:
    """Return the stable content key for a compiled prompt.

    sha256 over the exact prompt text, truncated to 16 hex chars — long
    enough that a collision inside one lane's lifetime of prompts is not a
    real concern, short enough to read in a log line. Same text → same hash
    across processes and sessions (the probe-exemption rule depends on it).
    """
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]


def build_prediction_block(rules: RenderRules, has_refs: bool) -> str:
    """Derive the pre-watch prediction block from the config taxonomy.

    Mechanical, deterministic (no LLM): every guarded taxonomy entry
    (``code_check`` / ``prompt_rule``) applicable to this run contributes one
    "expect" line stating its on-screen expectation and the guard's type;
    every applicable ``watch_only`` entry is listed under UNGUARDED as an
    open risk — flagged, never promised. ``refs_only`` classes appear only
    when the run carries reference images.

    The returned block is written to the run directory (``prediction.txt``)
    and embedded on the render sheet above the watch checklist, so the
    operator's verdict always tests a stated theory (Deming consult
    2026-07-22: turn Check into Study).
    """
    taxonomy = rules.pov_verdict()["defect_taxonomy"]
    guarded: list[str] = []
    unguarded: list[str] = []
    for slug, entry in taxonomy.items():
        if entry["applies"] == "refs_only" and not has_refs:
            continue
        if entry["guard"] == "watch_only":
            unguarded.append(f"- {slug}: {entry['description']} (no mechanical guard)")
        else:
            expectation = entry.get("expectation", f"no {slug}")
            guarded.append(f"- expect NOT {slug}: {expectation} [guard: {entry['guard']}]")
    lines = [
        "Prediction (the ruleset's own theory — judge the watch against this):",
        *guarded,
        "UNGUARDED open risks (watch is the only detector):",
        *unguarded,
    ]
    return "\n".join(lines)


def _rate(rules: RenderRules, resolution: str) -> float:
    """Return the measured per-second credit rate for ``resolution``.

    Reads the scene model's ``cost_estimate_credits.per_second_<resolution>``
    row. Loud KeyError-turned-ValueError on an unmeasured tier — a verdict
    must never tally spend from an invented rate (ADR-0007 cost governance).
    """
    model_id = rules.scene_model()
    try:
        return rules.model(model_id)["limits"]["cost_estimate_credits"][
            f"per_second_{resolution}"
        ]
    except KeyError as exc:
        raise ValueError(
            f"no measured {resolution} rate for {model_id} in render_rules.yaml — "
            f"cannot tally credits for this verdict"
        ) from exc


def derive_final_command(
    sanity_command: str, duration_seconds: int, rules: RenderRules
) -> tuple[str, str]:
    """Derive the final-resolution CLI command + cost line from the probe command.

    The final IS the probe command with only the resolution swapped to the
    config's ``final_resolution`` (same prompt, same refs, same duration —
    the probe-then-same-prompt contract, staged-director D7), plus a fresh
    cost line from the measured rate table (a released command always states
    its cost, ADR-0007).

    Returns:
        (final_command, cost_line).

    Raises:
        ValueError: if the sanity command carries no ``--resolution`` flag to
            swap, or the final resolution has no measured rate.
    """
    final_res = rules.pov_verdict()["final_resolution"]
    # Take the token AFTER the --resolution flag itself — never pattern-scan the
    # whole command, whose --prompt payload is free LLM prose that could carry a
    # stray resolution-looking word (review 2026-07-22).
    tokens = sanity_command.split()
    try:
        sanity_flag = tokens[tokens.index("--resolution") + 1]
    except (ValueError, IndexError):
        raise ValueError(
            f"cannot derive final command: no --resolution flag found in {sanity_command!r}"
        ) from None
    command = sanity_command.replace(
        f"--resolution {sanity_flag}", f"--resolution {final_res}"
    )
    rate = _rate(rules, final_res)
    cost = duration_seconds * rate
    cost_line = f"{final_res} final render: {duration_seconds}s x {rate}cr/s = {cost}cr"
    return command, cost_line


def _log_path(run_dir: Path) -> Path:
    """The lane-wide append-only log lives beside the run directories."""
    return run_dir.parent / _LOG_NAME


def _read_log(log_path: Path) -> list[POVVerdictRecord]:
    """Read every record from the lane log (empty list when no log exists yet)."""
    if not log_path.exists():
        return []
    return [
        POVVerdictRecord.model_validate_json(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _append_log(log_path: Path, record: POVVerdictRecord) -> None:
    """Append one record to the lane log as a single JSONL line."""
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def prior_pass_for_hash(log_path: Path, prompt_hash_value: str) -> bool:
    """Return whether the lane log holds a probe PASS for this exact prompt hash.

    The auto-exemption rule (grill Q2c): a re-render of an identical compiled
    prompt whose probe already passed skips re-probing. force_final events
    don't count — only a watched PASS is evidence.
    """
    return any(
        r.event == "verdict" and r.result == "pass" and r.prompt_hash == prompt_hash_value
        for r in _read_log(log_path)
    )


def _run_records(records: list[POVVerdictRecord], run: str) -> list[POVVerdictRecord]:
    return [r for r in records if r.run == run]


def _load_run_inputs(run_dir: Path) -> tuple[str, int, str | None]:
    """Read the verdict flow's inputs from the run directory's own artifacts.

    Returns (prompt_hash, duration_seconds, sanity_command). The prompt and
    script are the pipeline's committed artifacts (PRD: any run can be
    post-mortemed from its files); the sanity command comes from
    ``compiled.json`` when present (slice-③ runs) and is None on older run
    dirs — retro seeding still works there, only command release needs it.

    Raises:
        FileNotFoundError: if the run directory lacks prompt.txt/script.json —
            not a pipeline run directory.
    """
    prompt_text = (run_dir / "prompt.txt").read_text(encoding="utf-8")
    script = POVScript.model_validate_json(
        (run_dir / "script.json").read_text(encoding="utf-8")
    )
    sanity_command: str | None = None
    compiled_path = run_dir / "compiled.json"
    if compiled_path.exists():
        sanity_command = json.loads(compiled_path.read_text(encoding="utf-8"))["cli_command"]
    return prompt_hash(prompt_text), script.duration_seconds, sanity_command


def write_final(
    run_dir: Path, command: str, cost_line: str, final_resolution: str
) -> None:
    """Write the released final command (+ its cost line) to ``final_command.txt``.

    The ONE place the artifact's format lives — the verdict release paths and
    the driver's probe-exempt path all call this, so the file can never
    diverge between writers (review 2026-07-22). ``final_resolution`` names
    the released tier in the operating notes (the verdict-log reminder must
    match the command it sits under — it was hardcoded 720p before ticket 01)
    and drives the fallback guidance: a 1080p+refs job can be rejected by the
    model (n=1, RESEARCH-1080p-refs-limit.md) but failed jobs are uncharged,
    so the note says attempt first, fall back to NATIVE 720p — never an
    upscaled probe (post #3 blur lesson).
    """
    (run_dir / _FINAL_COMMAND_FILE).write_text(
        f"{command}\n\n# Cost: {cost_line}\n"
        f"# If this {final_resolution} job is REJECTED (refs at high res are "
        f"attempt-first; failed jobs are uncharged): re-run with --resolution "
        f"720p — native, NEVER an upscaled probe.\n"
        f"# Second take of this passed prompt = deliberate re-roll: use "
        f"--force-final (logged override).\n"
        f"# After watching the final, LOG IT (the log is how lessons stick):\n"
        f"#   uv run python scripts/pov.py verdict <run_dir> --pass "
        f"--resolution {final_resolution}\n"
        f"#   uv run python scripts/pov.py verdict <run_dir> --fail "
        f"--resolution {final_resolution} --defect <slug>\n",
        encoding="utf-8",
    )


def _park(run_dir: Path, records: list[POVVerdictRecord]) -> None:
    """Write the parked-story forensics file (PRD user story 21)."""
    prediction_path = run_dir / _PREDICTION_FILE
    forensics = {
        "parked_at": datetime.now(timezone.utc).isoformat(),
        "verdicts": [r.model_dump() for r in records],
        "defects": sorted({d for r in records for d in r.defects}),
        "credits_spent": sum(r.credits for r in records),
        "prediction": (
            prediction_path.read_text(encoding="utf-8") if prediction_path.exists() else None
        ),
    }
    (run_dir / _PARKED_FILE).write_text(
        json.dumps(forensics, indent=2), encoding="utf-8"
    )


def record_verdict(
    run_dir: Path,
    *,
    result: Literal["pass", "fail"],
    resolution: str,
    rules: RenderRules,
    defects: list[str] | None = None,
    note: str | None = None,
    tag: Literal["objective", "taste"] | None = None,
    retro: bool = False,
) -> VerdictOutcome:
    """Log one watched render's verdict and apply the gate/brake consequences.

    Flow: validate defects against the taxonomy (plus ``other``) → tally this
    render's credits (duration x measured rate) → append the record to the
    lane log → then, in order: park the story if this fail crossed the
    retake limit (first fail + ``max_failed_retakes`` more), emit a
    recurrence notice for every defect class that JUST reached 2 distinct
    runs, and on a PASS release the final-resolution command unless a brake
    (credit cap, parked story) refuses it.

    A fail must name at least one defect (an unnamed fail is uncountable —
    the log's whole point). ``tag`` defaults from the FIRST defect's taxonomy
    ``default_tag`` when the operator doesn't override (grill Q3/Deming
    tagging); pass verdicts carry no tag.

    Args:
        run_dir: The pipeline run directory being judged.
        result: The operator's watched verdict.
        resolution: The watched render's resolution (e.g. "480p") — keys the
            credit tally.
        rules: Loaded RenderRules (pov_verdict block + measured rates).
        defects: Taxonomy slugs (or ``other``) naming what failed. Required
            on a fail; must be empty/None on a pass.
        note: Free-text forensic detail (kept verbatim in the log).
        tag: Operator's objective-vs-taste override; None → first defect's
            taxonomy default.
        retro: Marks a seeded record reconstructed from a documented watched
            verdict (counts toward recurrence, stays distinguishable).

    Returns:
        A :class:`VerdictOutcome` describing what was logged and released.

    Raises:
        ValueError: on an unknown defect slug, a fail with no defects, or a
            pass that names defects.
        FileNotFoundError: if ``run_dir`` is not a pipeline run directory.
    """
    defects = list(defects or [])
    taxonomy = rules.pov_verdict()["defect_taxonomy"]
    unknown = [d for d in defects if d != _OTHER and d not in taxonomy]
    if unknown:
        raise ValueError(
            f"defect slug(s) {unknown} not in the defect taxonomy "
            f"(config/render_rules.yaml pov_verdict.defect_taxonomy) — use 'other' "
            f"with --note for a genuinely new failure mode"
        )
    if result == "fail" and not defects:
        raise ValueError("a fail verdict must name at least one defect (or 'other')")
    if result == "pass" and defects:
        raise ValueError("a pass verdict cannot name defects — log a fail instead")

    hash_value, duration, sanity_command = _load_run_inputs(run_dir)
    if tag is None and defects:
        first = defects[0]
        tag = taxonomy[first]["default_tag"] if first != _OTHER else "objective"

    record = POVVerdictRecord(
        event="verdict",
        run=run_dir.name,
        result=result,
        resolution=resolution,
        duration_seconds=duration,
        prompt_hash=hash_value,
        defects=defects,
        tag=tag if result == "fail" else None,
        note=note,
        credits=duration * _rate(rules, resolution),
        retro=retro,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    log_path = _log_path(run_dir)
    prior_records = _read_log(log_path)
    _append_log(log_path, record)
    all_records = [*prior_records, record]

    brakes = rules.pov_verdict()["spending_brakes"]
    outcome = VerdictOutcome(record=record)

    # Retro seeds are historical DATA, not gate events: they count toward
    # recurrence (PRD user story 14) but never park, release, or refuse —
    # those brakes are forward-looking, and firing them on reconstructed
    # history would e.g. park a run that in reality went on to pass.
    if result == "fail" and not retro:
        # Park check: first fail + max_failed_retakes more fails on this run.
        # Retro records are excluded from the COUNT too, not just from being
        # the parking trigger — a seeded historical fail must never cost a
        # story one of its live retakes (review 2026-07-22).
        run_fails = [
            r for r in _run_records(all_records, run_dir.name)
            if r.event == "verdict" and r.result == "fail" and not r.retro
        ]
        if len(run_fails) >= 1 + brakes["max_failed_retakes"]:
            _park(run_dir, _run_records(all_records, run_dir.name))
            outcome.parked = True

    # Recurrence gate: notice exactly when a defect class REACHES 2 distinct
    # runs (>=2 stays true afterwards, but the draft ask fires once, at the
    # crossing — repeated notices would nag without adding evidence).
    for defect in defects:
        if defect == _OTHER:
            continue
        runs_with_defect = {
            r.run
            for r in all_records
            if r.event == "verdict" and r.result == "fail" and defect in r.defects
        }
        prior_runs_with_defect = {
            r.run
            for r in prior_records
            if r.event == "verdict" and r.result == "fail" and defect in r.defects
        }
        if len(runs_with_defect) == 2 and len(prior_runs_with_defect) < 2:
            outcome.recurrence_notices.append(
                f"RECURRENCE: '{defect}' has now failed on 2 independent runs "
                f"({', '.join(sorted(runs_with_defect))}) — draft a rule row for "
                f"ratification (never auto-written)"
            )

    # Release path: probe PASS releases the final command, brakes permitting.
    if result == "pass" and not retro:
        spent = sum(r.credits for r in _run_records(all_records, run_dir.name))
        if (run_dir / _PARKED_FILE).exists():
            outcome.refusals.append("story is parked — no further commands released")
        elif spent >= brakes["per_story_credit_cap"]:
            outcome.refusals.append(
                f"per-story credit cap reached ({spent}cr >= "
                f"{brakes['per_story_credit_cap']}cr) — no further commands released"
            )
        elif sanity_command is None:
            outcome.refusals.append(
                "run directory has no compiled.json (pre-slice-③ run) — cannot "
                "derive the final command; re-run the pipeline for a releasable sheet"
            )
        else:
            command, cost_line = derive_final_command(sanity_command, duration, rules)
            write_final(
                run_dir, command, cost_line, rules.pov_verdict()["final_resolution"]
            )
            outcome.released_final_command = command

    return outcome


def force_release_final(run_dir: Path, *, rules: RenderRules) -> str:
    """Release the final command WITHOUT a probe pass, recording the bypass.

    Grill Q2b: the operator's judgment call (e.g. re-rolling a proven config)
    — allowed, but the bypass lands in the log as its own event type so a
    failed skipped-probe render is attributable. The force flag skips the
    PROBE only, never the brakes (PRD user story 18): parked stories and
    stories at/over the per-story credit cap refuse even a forced release —
    both brakes exist to stop exactly this spend.

    Returns:
        The released final command (also written to ``final_command.txt``).

    Raises:
        ValueError: if the story is parked, the per-story credit cap is
            reached, or the run predates compiled.json.
    """
    if (run_dir / _PARKED_FILE).exists():
        raise ValueError(
            f"story {run_dir.name} is parked (see {_PARKED_FILE}) — no further "
            f"commands released, forced or not"
        )
    brakes = rules.pov_verdict()["spending_brakes"]
    spent = sum(
        r.credits for r in _run_records(_read_log(_log_path(run_dir)), run_dir.name)
    )
    if spent >= brakes["per_story_credit_cap"]:
        raise ValueError(
            f"per-story credit cap reached ({spent}cr >= "
            f"{brakes['per_story_credit_cap']}cr) — no further commands released, "
            f"forced or not (--force-final skips the probe, never the cap)"
        )
    hash_value, duration, sanity_command = _load_run_inputs(run_dir)
    if sanity_command is None:
        raise ValueError(
            "run directory has no compiled.json (pre-slice-③ run) — cannot derive "
            "the final command"
        )
    command, cost_line = derive_final_command(sanity_command, duration, rules)
    write_final(run_dir, command, cost_line, rules.pov_verdict()["final_resolution"])
    _append_log(
        _log_path(run_dir),
        POVVerdictRecord(
            event="force_final",
            run=run_dir.name,
            result=None,
            resolution=None,
            duration_seconds=duration,
            prompt_hash=hash_value,
            note="probe skipped by operator (--force-final)",
            timestamp=datetime.now(timezone.utc).isoformat(),
        ),
    )
    return command
