"""POV candidate still generation + pick halt (D2 ticket 04).

.scratch/pov-d2-assets/PRD.md is the spec. A declared ``--object`` with no
promoted references does not ask the operator to source images (objects are
INVENTED — there is no canon to fetch): the pipeline generates candidate
stills via GPT Image 2, writes them into the object's ``candidates/`` area,
records the spend on the lane verdict log, and halts with a pick sheet. The
operator promotes keepers by moving a file up one directory, then runs
``pov.py assets <run_dir>`` to compile the run against the promoted refs.

Design constraints carried from the post #3 forensics (2026-07-22):

- Per-object ISOLATED stills, never the composed target frame — a composed
  reference identity-locks the whole frame and kills motion (probe B).
- One shared style clause verbatim across the batch so separately-generated
  objects read as one world (first-use coherence gate on the probe watch;
  documented fallback = composed still + element crops).
- The still prompt is a deterministic template over the script seat's
  world-element description — no new LLM seat (grill Q3). Template text is
  CONFIG DATA (``pov_assets`` block, render_rules.yaml): it is prompt
  content, expected to be tuned per watched evidence.
- Cost is stated before spend (ADR-0007); the spend lands on the lane
  verdict log as a ``still_gen`` event so the per-story credit brake sees it
  (PRD story 23 — brakes read real recorded spend).

The Higgsfield call is isolated behind ONE runner function
(:func:`higgsfield_still_runner`) so seam-1 tests fake it — the lane's
existing fake pattern, not a new seam class.
"""

from collections.abc import Callable
from pathlib import Path

from src.generation.pov.asset_check import DeclaredCharacter
from src.generation.pov.schemas import POVScript
from src.generation.render_adapters.rules import RenderRules

# A still runner: (prompt_text, destination_path) -> path actually written.
StillRunner = Callable[[str, Path], Path]

_CANDIDATES_DIR = "candidates"


class POVAssetPickNeeded(Exception):
    """Raised after candidate stills were generated: the run halts for the pick.

    Not a defect — the generate-auto/pick-HUMAN gate (staged-director D2)
    working as designed. Carries the printable pick sheet and the run
    directory the operator resumes from (``pov.py assets <run_dir>``).
    """

    def __init__(self, run_dir: Path, sheet_text: str) -> None:
        super().__init__(sheet_text)
        self.run_dir = run_dir
        self.sheet_text = sheet_text


def build_still_prompt(description: str, scene_setting: str, rules: RenderRules) -> str:
    """Compose one object's candidate-still prompt from the config template.

    Deterministic slot-fill over ``pov_assets.still_prompt_template``:
    ``{description}`` is the script seat's world-element identity prose,
    ``{vantage_phrase}`` derives from the script's scene setting (the object
    should be pictured as seen from the story's vantage, not a floating
    product shot), ``{style_clause}`` is the batch-shared register clause.
    The template itself carries the element-ref discipline (single element,
    no composed staging, no text) — config data, tuned per watched evidence.
    """
    assets = rules.pov_assets()
    vantage_phrase = assets["vantage_template"].replace("{scene_setting}", scene_setting)
    return (
        assets["still_prompt_template"]
        .replace("{description}", description.rstrip("."))
        .replace("{vantage_phrase}", vantage_phrase)
        .replace("{style_clause}", assets["style_clause"])
    )


def missing_promoted_refs(
    declared: list[DeclaredCharacter], refs_root: str | Path
) -> list[DeclaredCharacter]:
    """Return the declared entries with no PROMOTED reference files on disk.

    Same promoted-files-only predicate as the asset gate (subdirectories —
    the candidates/ area — never count), split out so the driver can route
    missing OBJECTS to generation instead of the gate's halt.
    """
    root = Path(refs_root)
    return [
        d for d in declared
        if not (root / d.slug).is_dir()
        or not any(p.is_file() for p in (root / d.slug).iterdir())
    ]


def still_cost_line(count: int, rules: RenderRules) -> tuple[float, str]:
    """Return (total_credits, printable cost line) for ``count`` candidate stills.

    Rate from the measured ``pov_verdict.still_generation_credits`` row —
    never an invented number (ADR-0007). The line is printed BEFORE any
    generation call.
    """
    rate = rules.pov_verdict()["still_generation_credits"]
    total = count * rate
    model = rules.pov_assets()["still_model"]
    return total, f"Candidate stills via {model}: {count} x {rate}cr = {total}cr"


def generate_candidates(
    script: POVScript,
    missing: list[DeclaredCharacter],
    refs_root: str | Path,
    rules: RenderRules,
    runner: StillRunner,
) -> list[Path]:
    """Generate one candidate still per missing object into its candidates/ area.

    Returns every written candidate path (declaration order). The runner does
    the actual image call (real: :func:`higgsfield_still_runner`; tests: a
    fake writing fixture bytes) — a runner failure propagates loud, no retry
    loop (operator reruns; failed Higgsfield jobs are uncharged).

    Raises:
        ValueError: if a missing object has no world_elements entry in
            ``script`` — the structural check upstream should have caught it;
            generating from nothing would burn credits on an unbriefed image.
    """
    by_slug = {e.slug: e for e in script.world_elements}
    written: list[Path] = []
    for declared in missing:
        element = by_slug.get(declared.slug)
        if element is None:
            raise ValueError(
                f"object {declared.slug!r} has no world_elements entry in the script — "
                f"cannot brief a candidate still (structural check should have caught this)"
            )
        prompt = build_still_prompt(element.description, script.scene_setting, rules)
        dest_dir = Path(refs_root) / declared.slug / _CANDIDATES_DIR
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{declared.slug}_candidate_1.png"
        written.append(runner(prompt, dest))
    return written


def pick_sheet(run_dir: Path, candidates: list[Path], refs_root: str | Path) -> str:
    """Compose the operator-facing pick sheet printed at the halt."""
    lines = "\n".join(f"- {p}" for p in candidates)
    return (
        "CANDIDATE STILLS GENERATED — run halted for your pick (no render "
        "commands released yet).\n\n"
        f"{lines}\n\n"
        "Promote a keeper by MOVING it up one directory (out of candidates/, "
        f"into its refs/<slug>/ directory under {refs_root}). Reject by leaving "
        "it where it is; regenerate by deleting it and re-running the pipeline.\n\n"
        "Then release the probe command against the promoted refs:\n"
        f"  uv run python scripts/pov.py assets {run_dir}"
    )


def higgsfield_still_runner(prompt: str, dest: Path) -> Path:
    """The real still runner: one GPT Image 2 generation via the Higgsfield CLI.

    Runs ``higgsfield generate create <still_model> --prompt ... --wait``,
    pulls the result URL from stdout, downloads it to ``dest``. Reuses the
    executor's hardened CLI/download helpers (shell-injection-safe argv,
    redirect-following download). Loud failure on a CLI error — the caller
    never retries (failed jobs are uncharged; the operator reruns).
    """
    # Local import: executor pulls in httpx/ffprobe machinery the pure/test
    # paths of this module never need.
    from src.generation.executor import _download, _extract_url, _run_cli, _sanitize_prompt

    rules = RenderRules()
    model = rules.pov_assets()["still_model"]
    stdout = _run_cli(
        [
            "higgsfield", "generate", "create", model,
            "--prompt", _sanitize_prompt(prompt),
            "--wait",
        ]
    )
    _download(_extract_url(stdout), str(dest))
    return dest
