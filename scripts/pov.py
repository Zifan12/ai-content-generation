"""
POV pipeline driver (ticket 03) — idea mode end-to-end (the tracer bullet).

    uv run python scripts/pov.py --idea "<full story concept>"

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

Topic mode (``--topic``, ticket 05) is NOT built here — there is no
``--topic`` flag on this CLI yet. ``run_pov_pipeline``'s ``pitcher``
parameter exists ONLY so idea mode's own test can assert it is never called;
it is a forward seam for ticket 05 to wire real calls into, not a stub
implementation.

Flow: operator idea -> POVPitch (code, no LLM) -> POVScriptWriter.develop
(ONE LLM call) -> POVScript -> compile_pov_prompt (ticket 02, deterministic
code) -> CompiledPOVPrompt -> build_render_sheet (ticket 03, deterministic
code) -> four files written under a slug-named run directory: pitch.json,
script.json, prompt.txt, render_sheet.md.

No structural validation runs here (per-beat action count, beat-count
budget, dialogue-never-final-beat, duration in {10, 15}) — ticket 04 owns
that bounded-repair loop. A script that violates one of those rules compiles
anyway in THIS ticket's driver; only compile_pov_prompt's own word-budget
check (60-100 words) can fail a run, and that failure is allowed to surface
loud here (no repair loop exists yet to catch it).

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
from datetime import datetime
from pathlib import Path

# scripts/ run as a file (uv run python scripts/pov.py), not as a package —
# same pattern as scripts/smoke_content_writer.py / scripts/label.py: sys.path[0]
# is the scripts/ directory when invoked this way, not the repo root, so
# `import src...` below would otherwise fail.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.generation.pov.compiler import compile_pov_prompt  # noqa: E402
from src.generation.pov.render_sheet import build_render_sheet  # noqa: E402
from src.generation.pov.schemas import POVPitch  # noqa: E402
from src.generation.render_adapters.rules import RenderRules  # noqa: E402

# The operator's --idea text carries the whole concept; who/where/turn exist
# only for topic-mode's slate scannability (PRD user story 3), which idea
# mode skips entirely — see module docstring for why this is a fixed note
# rather than an invented split of the operator's text.
_IDEA_MODE_NOTE = "(operator-provided via --idea; see what_happens for the full concept)"


def _pitch_from_idea(idea_text: str) -> POVPitch:
    """
    Wrap the operator's raw --idea text as the picked pitch, verbatim, with NO LLM call.

    who/where/turn cannot be code-derived from one free-form string without a
    fragile self-invented heuristic parser (splitting on punctuation/keywords
    would silently mis-split some ideas and never be validated against real
    ones) — module docstring explains why that path was rejected. Only
    what_happens carries real content; it is the operator's text unchanged.
    """
    return POVPitch(
        who=_IDEA_MODE_NOTE,
        where=_IDEA_MODE_NOTE,
        what_happens=idea_text,
        turn=_IDEA_MODE_NOTE,
    )


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
    idea: str,
    *,
    pitcher=None,
    output_dir: str | Path = "output/pov",
) -> Path:
    """
    Run idea mode end-to-end and write its run directory.

    Flow: operator idea -> POVPitch (code-copy, no LLM) ->
    ``script_writer.develop`` (ONE LLM call) -> POVScript ->
    ``compile_pov_prompt`` -> CompiledPOVPrompt -> ``build_render_sheet`` ->
    four files on disk.

    Args:
        script_writer: Anything with ``develop(pitch: POVPitch) -> POVScript``
            (real: ``POVScriptWriter``; tests: a fake recording calls).
        rules: A loaded RenderRules instance (pov_grammar + scene_lane).
        idea: The operator's ``--idea`` text — wrapped verbatim as the
            picked pitch (see ``_pitch_from_idea`` for the who/where/turn
            placeholder rationale).
        pitcher: UNUSED in idea mode — reserved for ticket 05's topic mode.
            Idea mode never calls it; a test may inject a call-counting fake
            here to prove that (module docstring).
        output_dir: Parent directory the run's slug-named subdirectory is
            created under.

    Returns:
        The created run directory (``output_dir/<slug>/``), containing
        ``pitch.json``, ``script.json``, ``prompt.txt``, ``render_sheet.md``.
    """
    pitch = _pitch_from_idea(idea)
    script = script_writer.develop(pitch)
    compiled = compile_pov_prompt(script, rules)
    sheet = build_render_sheet(pitch, script, compiled, rules)

    run_dir = Path(output_dir) / _run_slug(idea)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "pitch.json").write_text(pitch.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    (run_dir / "prompt.txt").write_text(compiled.prompt_text, encoding="utf-8")
    (run_dir / "render_sheet.md").write_text(sheet, encoding="utf-8")
    return run_dir


def main() -> None:
    """Parse CLI args and run idea mode with the real script writer + render rules."""
    from dotenv import load_dotenv

    load_dotenv("config/.env")
    # LLM-written prose can carry unicode; Windows stdout defaults to cp1252
    # and raises UnicodeEncodeError on it (same BUG-011-sibling fix as
    # smoke_content_writer.py / pitch_angles.py).
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(description="POV pipeline driver (idea mode).")
    parser.add_argument(
        "--idea",
        required=True,
        help="Full story concept — becomes the picked pitch verbatim, no slate.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/pov",
        help="Parent directory the run's slug-named subdirectory is created under.",
    )
    args = parser.parse_args()

    from src.generation.pov.script_writer import POVScriptWriter
    from src.providers.llm.factory import llm_for_seat

    script_writer = POVScriptWriter(llm=llm_for_seat("pov_script"))
    rules = RenderRules()
    run_dir = run_pov_pipeline(script_writer, rules, args.idea, output_dir=args.output_dir)
    print(f"\nRun directory: {run_dir}")
    print(f"Next: open {run_dir / 'render_sheet.md'} and follow the MANDATORY 480p pass.")


if __name__ == "__main__":
    main()
