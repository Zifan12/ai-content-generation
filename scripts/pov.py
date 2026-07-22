"""
POV pipeline driver (tickets 03 + 05) — idea mode and topic mode end-to-end.

    uv run python scripts/pov.py --idea "<full story concept>"
    uv run python scripts/pov.py --topic "<bare topic seed>"

Idea mode: the operator's ``--idea`` text becomes the picked pitch VERBATIM —
no pitcher call, no slate (PRD Solution: "operator's text IS the pitch, slate
skipped"). POVPitch requires four separate fields (who/where/what_happens/
turn) that exist so a SLATE ENTRY is scannable in seconds (PRD user story 3);
idea mode skips the slate entirely, and there is no LLM call available (by
design — "no pitcher call") to split free-form operator text into those four
dimensions without inventing a fragile heuristic parser (rejected — see
_pitch_from_idea below). ``what_happens`` therefore carries the operator's
text byte-for-byte (the "code-copy proof" this ticket's acceptance criteria
names); who/where/turn carry a fixed pointer-back note instead. This is
ticket 03's own call — ticket 02's schema docstring explicitly left the
who-derivation open.

Topic mode (ticket 05): the pitcher LLM seat (``src/generation/pov/
pitcher.py``) proposes a 3-5 pitch POVPitchSlate for the operator's bare
``--topic`` text; the operator picks ONE by number (interactively via
``choice_provider``). The picked ``POVPitch`` is code-copied into every
downstream artifact exactly like idea mode's — the pitcher's OWN output is
naturally an LLM authorship (it is the pitch stage), but nothing past the
pick re-derives or paraphrases it. The full slate (picked + unpicked) is
persisted as ``slate.json`` in the run directory for post-mortem.

``--idea`` and ``--topic`` are mutually exclusive on the CLI (argparse's own
mutually-exclusive group, required — enforced natively, no custom check
needed); ``run_pov_pipeline`` re-checks the same exactly-one invariant at the
function seam so a direct/test caller gets the same loud failure.

Flow (both modes converge after the pitch is picked): POVPitch -> craft_enforcement.
develop_valid_script (POVScriptWriter.develop, ONE structural check, and — on
a violation — ONE bounded POVScriptWriter.repair call, ticket 04) -> POVScript
-> compile_pov_prompt (ticket 02, deterministic code) -> CompiledPOVPrompt ->
build_render_sheet (ticket 03, deterministic code) -> files written under a
slug-named run directory: (topic mode only) slate.json, then pitch.json,
script.json, prompt.txt, render_sheet.md.

Structural validation (per-beat action count, beat-count budget,
dialogue-never-final-beat, duration in {10, 15}) now runs on every script via
``develop_valid_script`` (ticket 04) — a script that still violates a rule
after its one bounded repair raises ``POVStructuralViolationError`` and this
driver lets it surface loud (no silent pass-through into the compiler). A
failure at this point loses the slate that was already paid for
(``slate.json`` is written only on success, matching the existing
writes-nothing-on-failure invariant idea mode already has) — a deliberate,
narrow scope call: durability of a slate across a downstream crash is a
separate feature this ticket does not ask for.
compile_pov_prompt's own word-budget check (60-100 words) is a separate,
unrelated failure that can still surface loud here too.

LIVE SMOKE (not run in CI — spends one real LLM call, zero render credits):
    uv run python scripts/pov.py --idea "I dive into a sunken WWII wreck and \
find a still-ticking pocket watch wedged in the captain's cabin door"
The run directory prints on success; open its render_sheet.md and follow the
MANDATORY 480p sanity pass before any 720p/1080p spend.
"""

import argparse
import re
import sys
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

# scripts/ run as a file (uv run python scripts/pov.py), not as a package —
# same pattern as scripts/smoke_content_writer.py / scripts/label.py: sys.path[0]
# is the scripts/ directory when invoked this way, not the repo root, so
# `import src...` below would otherwise fail.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generation.pov.asset_check import (  # noqa: E402
    POVAssetRequestNeeded,
    check_assets,
    parse_character_args,
)
from src.generation.pov.compiler import compile_pov_prompt  # noqa: E402
from src.generation.pov.craft_enforcement import develop_valid_script  # noqa: E402
from src.generation.pov.render_sheet import build_render_sheet  # noqa: E402
from src.generation.pov.schemas import POVPitch, POVPitchSlate  # noqa: E402
from src.generation.pov.verdict import (  # noqa: E402
    build_prediction_block,
    derive_final_command,
    force_release_final,
    prior_pass_for_hash,
    prompt_hash,
    record_verdict,
)
from src.generation.render_adapters.rules import RenderRules  # noqa: E402

# The operator's --idea text carries the whole concept; who/where/turn exist
# only for topic-mode's slate scannability (PRD user story 3), which idea
# mode skips entirely — see module docstring for why this is a fixed note
# rather than an invented split of the operator's text.
_IDEA_MODE_NOTE = "(operator-provided via --idea; see what_happens for the full concept)"

# money_shot's own placeholder (ticket 07): unlike who/where/turn, this note is
# ALSO read by the script seat's craft rule ("if money_shot is a placeholder
# note ... infer the peak"), so it states the fallback contract instead of just
# pointing back at what_happens.
_MONEY_SHOT_UNSET_NOTE = (
    "(not stated — script stage infers the peak from what_happens; "
    "check the climax beats on the sheet)"
)


def _pitch_from_idea(idea_text: str, money_shot: str | None = None) -> POVPitch:
    """
    Wrap the operator's raw --idea text as the picked pitch, verbatim, with NO LLM call.

    who/where/turn cannot be code-derived from one free-form string without a
    fragile self-invented heuristic parser (splitting on punctuation/keywords
    would silently mis-split some ideas and never be validated against real
    ones) — module docstring explains why that path was rejected. Only
    what_happens carries real content; it is the operator's text unchanged.

    ``money_shot`` (ticket 07) is the operator's ``--money-shot`` text
    byte-verbatim when given — the single image the video exists to deliver —
    or the ``_MONEY_SHOT_UNSET_NOTE`` placeholder when not, which tells the
    script seat to infer the peak (its inference is then visible as the
    climax beats on the sheet, still a pre-spend check).
    """
    return POVPitch(
        who=_IDEA_MODE_NOTE,
        where=_IDEA_MODE_NOTE,
        what_happens=idea_text,
        turn=_IDEA_MODE_NOTE,
        money_shot=money_shot if money_shot is not None else _MONEY_SHOT_UNSET_NOTE,
    )


def _print_slate(slate: POVPitchSlate) -> None:
    """Print the numbered POV pitch slate for the operator to choose from."""
    for i, pitch in enumerate(slate.pitches, start=1):
        print(f"\n[{i}] who:  {pitch.who}")
        print(f"     where: {pitch.where}")
        print(f"     what:  {pitch.what_happens}")
        print(f"     turn:  {pitch.turn}")
        print(f"     money: {pitch.money_shot}")


def _pick_pitch(slate: POVPitchSlate, choice_provider: Callable[[], str] | None) -> POVPitch:
    """
    Read the operator's numeric pick from ``choice_provider`` and return that pitch.

    Single-call, loud-fail (mirrors the ticket's silence on a retry UX — a
    skip/re-pitch menu is scripts/pitch_angles.py's scope, not this ticket's):
    an unset ``choice_provider``, a non-numeric answer, or a number outside
    the slate's range all raise ``ValueError`` naming the problem rather than
    re-prompting or silently defaulting.

    Args:
        slate: The pitcher's full slate (3-5 pitches).
        choice_provider: Zero-arg callable returning the operator's typed
            pick as a string (real: ``lambda: input(...)``; tests: a fake
            returning a fixed string).

    Returns:
        The picked ``POVPitch``.

    Raises:
        ValueError: if ``choice_provider`` is None, or its answer is not a
            valid 1-based index into ``slate.pitches``.
    """
    if choice_provider is None:
        raise ValueError("choice_provider is required for topic mode (interactive pick)")
    choice = choice_provider().strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(slate.pitches)):
        raise ValueError(
            f"invalid pick {choice!r} — enter a pitch number 1-{len(slate.pitches)}"
        )
    return slate.pitches[int(choice) - 1]


def _run_slug(idea_text: str) -> str:
    """
    Build a filesystem-safe, collision-free run directory name.

    Timestamp (human-sortable) + up to 40 chars of slugified idea words, plus
    a short uuid4 suffix — the timestamp alone is not collision-proof (two
    calls in the same wall-clock second, e.g. back-to-back runs in a test or
    a fast rerun, would otherwise land on the identical slug and silently
    overwrite the first run's artifacts).
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    words = re.sub(r"[^a-z0-9]+", "_", idea_text.lower()).strip("_").split("_")
    short = "_".join(w for w in words if w)[:40] or "idea"
    return f"{ts}_{short}_{uuid.uuid4().hex[:6]}"


def run_pov_pipeline(
    script_writer,
    rules: RenderRules,
    idea: str | None = None,
    *,
    pitcher=None,
    topic: str | None = None,
    choice_provider: Callable[[], str] | None = None,
    money_shot: str | None = None,
    characters: list[str] | None = None,
    refs_root: str | Path = "refs",
    output_dir: str | Path = "output/pov",
) -> Path:
    """
    Run idea mode OR topic mode end-to-end and write its run directory.

    Exactly one of ``idea`` (idea mode, ticket 03) or ``topic`` (topic mode,
    ticket 05) must be given. Idea mode wraps the operator's text verbatim as
    the picked pitch (no LLM call). Topic mode calls ``pitcher.pitch(topic)``
    for a 3-5 pitch slate, prints it, reads the operator's numeric pick via
    ``choice_provider`` (see ``_pick_pitch``), and code-copies that one pitch
    forward — identical to idea mode from that point on.

    Flow after the pitch is picked (both modes): POVPitch ->
    ``craft_enforcement.develop_valid_script`` (``script_writer.develop``,
    one structural check, and on a violation ONE bounded
    ``script_writer.repair`` call, ticket 04) -> POVScript ->
    ``compile_pov_prompt`` -> CompiledPOVPrompt -> ``build_render_sheet`` ->
    files on disk.

    Args:
        script_writer: Anything with ``develop(pitch: POVPitch) -> POVScript``
            and ``repair(pitch, failed_script, violations) -> POVScript``
            (real: ``POVScriptWriter``; tests: a fake recording calls).
        rules: A loaded RenderRules instance (pov_grammar + scene_lane).
        idea: The operator's ``--idea`` text — wrapped verbatim as the
            picked pitch (see ``_pitch_from_idea`` for the who/where/turn
            placeholder rationale). Mutually exclusive with ``topic``.
        pitcher: Anything with ``pitch(topic: str) -> POVPitchSlate`` (real:
            ``POVPitcher``; tests: a fake recording calls). REQUIRED when
            ``topic`` is set; unused (and never called — a test may inject a
            call-counting fake to prove that) in idea mode.
        topic: The operator's bare ``--topic`` text — triggers topic mode.
            Mutually exclusive with ``idea``.
        choice_provider: Zero-arg callable returning the operator's typed
            pick as a string. REQUIRED when ``topic`` is set (see
            ``_pick_pitch``); unused in idea mode.
        money_shot: Idea mode only (ticket 07): the operator's ``--money-shot``
            text, carried byte-verbatim as the pitch's money_shot. None →
            the unset placeholder note (script seat infers the peak).
            Invalid with ``topic`` — topic-mode pitches carry their own.
        characters: Optional ``--character <slug>[:role]`` declarations
            (ticket 10). Parsed and asset-gated BEFORE any LLM seat runs —
            a declared character with no references on disk halts the run
            with a request sheet and costs zero LLM calls. Validated
            reference paths flow to the compiler (``--image`` flags, upload
            order = imageN) and the render sheet.
        refs_root: Root directory holding per-character reference libraries
            (``<refs_root>/<slug>/``). The repo convention is ``refs/``.
        output_dir: Parent directory the run's slug-named subdirectory is
            created under.

    Returns:
        The created run directory (``output_dir/<slug>/``), containing (topic
        mode only) ``slate.json``, then ``pitch.json``, ``script.json``,
        ``prompt.txt``, ``render_sheet.md``.

    Raises:
        ValueError: if neither or both of ``idea``/``topic`` are given, if
            ``topic`` is set with no ``pitcher``, if the operator's pick
            (via ``choice_provider``) is missing or invalid, or if a
            declared character's reference directory fails validation.
        POVAssetRequestNeeded: if a declared character has no references on
            disk yet — carries the printable request sheet; zero LLM calls
            were made.
        POVStructuralViolationError: if the script still violates a
            structural rule after its one bounded repair (ticket 04) —
            surfaces loud, no run directory is written.
    """
    if (idea is None) == (topic is None):
        raise ValueError("exactly one of idea or topic must be given to run_pov_pipeline")
    if money_shot is not None and topic is not None:
        raise ValueError(
            "money_shot is an idea-mode input — topic-mode pitches carry their own "
            "money_shot from the pitcher (ticket 07)"
        )

    # Asset gate FIRST (tickets 10+11): a declared character with no references
    # halts here — before the pitcher or script seat can spend an LLM call.
    resolved: list = []
    if characters:
        resolved = check_assets(parse_character_args(characters), Path(refs_root))
    ref_paths = [path for character in resolved for path in character.ref_paths]
    ref_bound = tuple(character.slug for character in resolved)

    slate: POVPitchSlate | None = None
    if topic is not None:
        if pitcher is None:
            raise ValueError("pitcher is required when topic is set (topic mode)")
        slate = pitcher.pitch(topic)
        _print_slate(slate)
        pitch = _pick_pitch(slate, choice_provider)
    else:
        assert idea is not None  # narrowed by the exactly-one check above
        pitch = _pitch_from_idea(idea, money_shot)

    script = develop_valid_script(script_writer, pitch, rules, ref_bound=ref_bound)
    compiled = compile_pov_prompt(script, rules, bound_characters=resolved)

    # Slice ③ probe gate inputs: the ruleset's pre-watch prediction (Deming
    # Study step) and the identical-prompt-hash probe exemption (grill Q2c) —
    # the lane verdict log lives beside the run directories.
    prediction = build_prediction_block(rules, has_refs=bool(ref_paths))
    lane_log = Path(output_dir) / "verdicts.jsonl"
    probe_exempt = prior_pass_for_hash(lane_log, prompt_hash(compiled.prompt_text))
    sheet = build_render_sheet(
        pitch,
        script,
        compiled,
        rules,
        ref_paths=ref_paths,
        prediction_block=prediction,
        probe_exempt=probe_exempt,
    )

    slug_source = idea if idea is not None else topic
    assert slug_source is not None  # narrowed by the exactly-one check above
    run_dir = Path(output_dir) / _run_slug(slug_source)
    run_dir.mkdir(parents=True, exist_ok=True)
    if slate is not None:
        (run_dir / "slate.json").write_text(slate.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "pitch.json").write_text(pitch.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "prompt.txt").write_text(compiled.prompt_text, encoding="utf-8")
    # compiled.json (slice ③): the verdict flow re-derives the final command
    # from the probe command here — without it a run is watchable but never
    # releasable (pre-slice-③ dirs hit exactly that, by design).
    (run_dir / "compiled.json").write_text(compiled.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "prediction.txt").write_text(prediction, encoding="utf-8")
    (run_dir / "render_sheet.md").write_text(sheet, encoding="utf-8")
    if probe_exempt:
        command, cost_line = derive_final_command(
            compiled.cli_command, script.duration_seconds, rules
        )
        (run_dir / "final_command.txt").write_text(
            f"{command}\n\n# Cost: {cost_line}\n", encoding="utf-8"
        )
    return run_dir


def _build_parser() -> argparse.ArgumentParser:
    """
    Build the CLI arg parser (idea mode + topic mode).

    Split out from ``main()`` so it can be unit-tested (mutually-exclusive /
    required-group behavior) without dragging in ``dotenv``, real LLM seats,
    or stdout reconfiguration. ``--idea`` and ``--topic`` live in a required
    mutually-exclusive group — argparse itself enforces "exactly one of the
    two" and raises (``SystemExit``, exit code 2) with a loud message on
    either "both given" or "neither given"; no custom check is needed here
    (``run_pov_pipeline`` re-checks the same invariant at the function seam
    for direct/test callers that bypass this parser entirely).
    """
    parser = argparse.ArgumentParser(description="POV pipeline driver (idea mode + topic mode).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--idea",
        help="Full story concept — becomes the picked pitch verbatim, no slate.",
    )
    group.add_argument(
        "--topic",
        help="Bare topic seed — the pitcher seat proposes a 3-5 pitch slate to pick from.",
    )
    parser.add_argument(
        "--money-shot",
        dest="money_shot",
        help=(
            "Idea mode only: the single image the video exists to deliver, in your own "
            "words (carried verbatim). Unset: the script stage infers the peak — check "
            "the climax beats on the sheet."
        ),
    )
    parser.add_argument(
        "--character",
        action="append",
        metavar="SLUG[:ROLE]",
        help=(
            "Canon subject requiring reference images (repeatable). ROLE is "
            "'protagonist' (default — you ARE the character, limbs only) or "
            "'in_frame' (the character stands in front of the camera). Missing "
            "refs/<slug>/ halts the run with a request sheet before any LLM spend."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="output/pov",
        help="Parent directory the run's slug-named subdirectory is created under.",
    )
    return parser


def _build_verdict_parser() -> argparse.ArgumentParser:
    """
    Build the ``verdict`` subcommand's parser (slice ③).

    Exactly one of ``--pass`` / ``--fail`` / ``--force-final``: the first two
    log a watched verdict (a probe PASS releases the final command; a FAIL
    counts its defects toward the recurrence gate), the third releases the
    final WITHOUT a probe pass and logs the bypass (grill Q2b). ``--defect``
    is repeatable and must name taxonomy slugs (or ``other``);
    ``--objective``/``--taste`` override the taxonomy's default tag.
    """
    parser = argparse.ArgumentParser(
        prog="pov.py verdict",
        description="Log a watched render's verdict for a POV run directory (slice ③).",
    )
    parser.add_argument("run_dir", help="The pipeline run directory that was rendered/watched.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pass", dest="passed", action="store_true", help="Watched: keeper.")
    group.add_argument("--fail", dest="failed", action="store_true", help="Watched: defective.")
    group.add_argument(
        "--force-final",
        dest="force_final",
        action="store_true",
        help="Release the final command WITHOUT a probe pass (logged as a bypass).",
    )
    parser.add_argument(
        "--resolution",
        default="480p",
        help="Resolution of the render you watched (keys the credit tally). Default 480p.",
    )
    parser.add_argument(
        "--defect",
        action="append",
        dest="defects",
        metavar="SLUG",
        help=(
            "Defect class from pov_verdict.defect_taxonomy (repeatable); use "
            "'other' + --note for a brand-new failure mode. Required with --fail."
        ),
    )
    parser.add_argument("--note", help="Free-text forensic detail, kept verbatim in the log.")
    tag_group = parser.add_mutually_exclusive_group()
    tag_group.add_argument(
        "--objective", action="store_true", help="Tag: operationally defined defect."
    )
    tag_group.add_argument("--taste", action="store_true", help="Tag: subjective judgment call.")
    parser.add_argument(
        "--retro",
        action="store_true",
        help="Seeded record reconstructed from a documented past watch (counts toward recurrence).",
    )
    return parser


def _main_verdict(argv: list[str]) -> None:
    """Run the ``verdict`` subcommand: log the verdict / force-release and print outcomes."""
    args = _build_verdict_parser().parse_args(argv)
    rules = RenderRules()
    run_dir = Path(args.run_dir)

    if args.force_final:
        command = force_release_final(run_dir, rules=rules)
        print("Probe SKIPPED — bypass logged. Final command (also in final_command.txt):")
        print(command)
        return

    tag = "objective" if args.objective else "taste" if args.taste else None
    outcome = record_verdict(
        run_dir,
        result="pass" if args.passed else "fail",
        resolution=args.resolution,
        rules=rules,
        defects=args.defects,
        note=args.note,
        tag=tag,
        retro=args.retro,
    )
    print(f"Logged {outcome.record.result} for {run_dir.name} ({outcome.record.credits}cr).")
    for notice in outcome.recurrence_notices:
        print(notice)
    for refusal in outcome.refusals:
        print(f"REFUSED: {refusal}")
    if outcome.parked:
        print(f"STORY PARKED — forensics written to {run_dir / 'parked.json'}.")
    if outcome.released_final_command:
        print("Probe PASS — final command released (also in final_command.txt):")
        print(outcome.released_final_command)


def main() -> None:
    """Parse CLI args and run idea mode or topic mode with the real seats + render rules."""
    from dotenv import load_dotenv

    load_dotenv("config/.env")
    # LLM-written prose can carry unicode; Windows stdout defaults to cp1252
    # and raises UnicodeEncodeError on it (same BUG-011-sibling fix as
    # smoke_content_writer.py / pitch_angles.py).
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    # Subcommand dispatch (slice ③): `pov.py verdict <run_dir> ...` — needs no
    # LLM seats and must work with zero API keys, hence the early exit. The
    # flag-style invocation (`pov.py --idea/--topic ...`) stays byte-compatible.
    if len(sys.argv) > 1 and sys.argv[1] == "verdict":
        _main_verdict(sys.argv[2:])
        return

    args = _build_parser().parse_args()

    from src.generation.pov.script_writer import POVScriptWriter
    from src.providers.llm.factory import llm_for_seat

    script_writer = POVScriptWriter(llm=llm_for_seat("pov_script"))
    rules = RenderRules()

    if args.topic is not None:
        from src.generation.pov.pitcher import POVPitcher

        pitcher = POVPitcher(llm=llm_for_seat("pov_pitcher"))
        choice_provider = lambda: input("\nPick a pitch by number: ")  # noqa: E731
    else:
        pitcher = None
        choice_provider = None

    try:
        run_dir = run_pov_pipeline(
            script_writer,
            rules,
            args.idea,
            pitcher=pitcher,
            topic=args.topic,
            choice_provider=choice_provider,
            money_shot=args.money_shot,
            characters=args.character,
            output_dir=args.output_dir,
        )
    except POVAssetRequestNeeded as exc:
        # Not a defect — the operator hasn't supplied reference images yet.
        # Print the request sheet and exit nonzero (nothing was run or spent).
        print(f"\n{exc.sheet_text}")
        sys.exit(1)
    print(f"\nRun directory: {run_dir}")
    print(f"Next: open {run_dir / 'render_sheet.md'} and follow the MANDATORY 480p pass.")


if __name__ == "__main__":
    main()
