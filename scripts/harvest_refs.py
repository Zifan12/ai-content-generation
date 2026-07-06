"""
Reference harvest CLI (Task 12): turn an approved pitch into human-approved
reference frames at data/reference_cache/<pitch_id>/approved_candidates/.

Loads the approved AnglePitchRecord's FULL story (story_json -> StoryPitch)
plus its event's context_bundle, then runs the harvester once per
needs_reference character: LLM query plan -> yt-dlp search -> shortlist ->
LLM pick -> download -> ffmpeg frame extraction -> heuristic prefilter ->
vision-LLM frame judge -> angle-diverse ranking -> approval folder +
provenance manifest.

By default prints the LLM cost estimate and stops (no network, no LLM calls,
nothing spent). --real prints the estimate, requires an interactive 'yes',
then runs the live harvest (yt-dlp/ffmpeg are free/local; LLM calls are
flash-tier cents — L7/ADR-0007 still says estimate-then-confirm).

After a run, prune the approved_candidates/<character>/ folders by hand
(delete rejects, drop in your own images), then feed the survivors to the
writer via the printed smoke_content_writer.py --refs command.

USAGE:
  uv run python scripts/harvest_refs.py --pitch-id 12
  uv run python scripts/harvest_refs.py --pitch-id 12 --real
"""

import argparse
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv("config/.env")

# Windows console defaults to cp1252; titles/reasons from YouTube and the LLM
# carry emoji and typographic unicode (BUG-011 sibling) — replace, don't crash.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.database import SessionLocal  # noqa: E402
from src.models.angle_pitch import AnglePitchRecord  # noqa: E402
from src.models.trending_event import TrendingEventRecord  # noqa: E402
from src.monitor.schemas import ContextBundle, StoryPitch  # noqa: E402
from src.providers.llm.openrouter_llm import OpenRouterLLM  # noqa: E402
from src.reference.frame_judge import FrameJudge  # noqa: E402
from src.reference.harvester import Harvester  # noqa: E402
from src.reference.query_planner import QueryPlanner  # noqa: E402
from src.reference.video_finder import VideoPicker  # noqa: E402

_CONFIG_PATH = "config/reference_harvest.yaml"


def _build_parser() -> argparse.ArgumentParser:
    """Build the harvest-script argument parser.

    ``--pitch-id`` names the approved AnglePitchRecord whose story_json and
    event context drive the query planner. ``--real`` gates every network/LLM
    call behind an explicit confirm (mirror of smoke_content_writer.py's
    dry-by-default convention).
    """
    parser = argparse.ArgumentParser(
        description="Harvest human-approvable reference frames for a pitch."
    )
    parser.add_argument(
        "--pitch-id",
        type=int,
        required=True,
        help="Approved AnglePitchRecord id; its story_json names the characters.",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Run the live harvest (yt-dlp + ffmpeg + LLM calls). Prints the "
        "cost estimate first and requires an interactive 'yes'.",
    )
    return parser


def load_pitch(db, pitch_id: int) -> AnglePitchRecord:
    """Load an AnglePitchRecord by primary key, or exit loudly if it is absent.

    Args:
        db: An open SQLAlchemy session.
        pitch_id: Primary key of the angle pitch to load.

    Returns:
        The AnglePitchRecord row.

    Raises:
        SystemExit: if no row with that id exists — a clear operator error
            rather than an opaque AttributeError downstream.
    """
    pitch = db.get(AnglePitchRecord, pitch_id)
    if pitch is None:
        raise SystemExit(f"No AnglePitchRecord with id={pitch_id} — nothing to harvest.")
    return pitch


def resolve_pitch(args, db) -> tuple[StoryPitch, str]:
    """Load the pitch's full story plus its event's context block.

    Reads ``story_json`` (the complete StoryPitch the pitcher persisted) and
    validates it back into the typed model — NULL story_json is a hard error,
    same policy as smoke_content_writer.py. The event's ``context_bundle`` is
    optional: a pitch whose event never ran the context agent harvests on
    pitch fields alone (the planner prompt treats the context block as
    optional grounding).

    Args:
        args: Parsed argparse namespace (uses ``pitch_id``).
        db: An open SQLAlchemy session.

    Returns:
        ``(story_pitch, context_block)`` ready for ``Harvester.run``;
        ``context_block`` is "" when no bundle exists.

    Raises:
        SystemExit: if the row is missing, or its story_json is NULL.
    """
    record = load_pitch(db, args.pitch_id)
    if record.story_json is None:
        raise SystemExit(
            f"AnglePitchRecord {args.pitch_id} has no story_json (pre-Stage-B "
            "legacy row) — re-pitch it; the logline-only path is retired."
        )
    pitch = StoryPitch.model_validate(record.story_json)
    print(f"[pitch] #{args.pitch_id}: {pitch.logline}")

    context_block = ""
    event = db.get(TrendingEventRecord, record.trending_event_id)
    if event is not None and event.context_bundle:
        context_block = ContextBundle.model_validate(
            event.context_bundle
        ).to_context_block()
    print(f"[context] {'present' if context_block else 'none (pitch fields only)'}")
    return pitch, context_block


def print_cost_estimate(pitch: StoryPitch, config: dict) -> int:
    """Print the LLM call estimate BEFORE anything runs (L7/ADR-0007).

    yt-dlp and ffmpeg are free/local; the paid surface is flash-tier LLM
    calls: one planner + one picker text call per character, plus up to
    ``max_judge_frames`` vision calls per character.

    Returns:
        The number of characters that will be harvested.
    """
    n_chars = sum(c.needs_reference for c in pitch.characters)
    max_judge = config["max_judge_frames"]
    print(
        f"[estimate] {n_chars} character(s) x (1 planner + 1 picker + "
        f"<={max_judge} judge frames) = <={n_chars * (2 + max_judge)} "
        f"flash-tier LLM calls (single-digit cents/character; "
        f"models: {config['planner_model']} / {config['judge_model']})"
    )
    return n_chars


def main() -> None:
    """Parse args, print the cost estimate, and (with --real + confirm) run
    the harvest and print per-character results + the follow-up command."""
    args = _build_parser().parse_args()

    with open(_CONFIG_PATH, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    db = SessionLocal()
    try:
        pitch, context_block = resolve_pitch(args, db)
    finally:
        db.close()

    n_chars = print_cost_estimate(pitch, config)
    if n_chars == 0:
        raise SystemExit("No needs_reference characters in this pitch — nothing to do.")

    if not args.real:
        print("\nDry run — no calls made. Re-run with --real to harvest.")
        return

    answer = input("\nRun the live harvest with these LLM calls? Type 'yes' to proceed: ")
    if answer.strip().lower() != "yes":
        raise SystemExit("Aborted before any call — nothing spent.")

    harvester = Harvester(
        planner=QueryPlanner(llm=OpenRouterLLM(model=config["planner_model"])),
        picker=VideoPicker(llm=OpenRouterLLM(model=config["picker_model"])),
        judge=FrameJudge(llm=OpenRouterLLM(model=config["judge_model"])),
        config=config,
    )
    results = harvester.run(pitch, context_block, args.pitch_id)

    print("\n" + "=" * 70)
    approved_dirs: list[str] = []
    for result in results:
        print(f"[{result.status}] {result.character_name}: {result.detail}")
        print(f"  manifest: {result.manifest_path}")
        if result.approved_dir:
            print(f"  approved: {result.approved_dir}")
            approved_dirs.append(result.approved_dir)
    print("=" * 70)

    if approved_dirs:
        ref_args = " ".join(
            str(p) for d in approved_dirs for p in sorted(Path(d).glob("*.png"))
        )
        print(
            "\nPrune the approved folders (delete rejects), then run:\n"
            f"  uv run python scripts/smoke_content_writer.py "
            f"--pitch-id {args.pitch_id} --refs {ref_args}"
        )
    else:
        print(
            "\nNo approved frames — fall back to manual refs "
            "(hand-picked key art via --refs), never render ungrounded (L3)."
        )


if __name__ == "__main__":
    main()
