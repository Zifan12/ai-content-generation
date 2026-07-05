"""
End-to-end smoke for the multi-shot pipeline (pitch → write → render_jobs → cost).

Loads an approved AnglePitchRecord's FULL story (story_json → StoryPitch — the
Stage-1/Stage-2 bridge), runs the two-call writer, composes grouped render jobs,
and prints the per-job credit estimate. Reference key-art paths are REQUIRED
(grounding is mandatory, DECISIONS_LOCKED L3).

By default runs dry_run (cost estimate only, no credits spent). --real prints the
credit table, requires an interactive 'yes', then renders every job (with resume
manifest), synthesizes narration (Higgsfield text2speech_v2, ~0.15cr/line), and
assembles the final mp4.

USAGE:
  uv run python scripts/smoke_content_writer.py --pitch-id 12 --refs refs/eve_1.jpg refs/eve_2.jpg
  uv run python scripts/smoke_content_writer.py --pitch-id 12 --refs refs/eve_1.jpg --real
  uv run python scripts/smoke_content_writer.py --pitch-id 12 --refs refs/eve_1.jpg --real --bgm music.mp3

OUTPUT:
  Prints the full MultiShotPackage (per-shot prompts, routing, groups, narration,
  caption) and the credit table; in --real mode also the per-clip paths and the
  assembled final.mp4. A timestamped transcript is saved to output/smoke_runs/.
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("config/.env")

from src.database import SessionLocal  # noqa: E402
from src.generation.assembly import assemble  # noqa: E402
from src.generation.content_writer import ContentWriter  # noqa: E402
from src.generation.executor import execute  # noqa: E402
from src.providers.tts.higgsfield_tts import HiggsfieldTTS  # noqa: E402
from src.generation.render_adapters.adapter import render_jobs  # noqa: E402
from src.generation.render_adapters.rules import RenderRules  # noqa: E402
from src.models.angle_pitch import AnglePitchRecord  # noqa: E402
from src.monitor.schemas import StoryPitch  # noqa: E402
from src.providers.llm.factory import llm_for_seat  # noqa: E402


class _Tee:
    """Duplicate every write to two streams (live console + the record file)."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)

    def flush(self):
        for s in self._streams:
            s.flush()


def _git_sha() -> str:
    """Return the current short git SHA, or 'nogit' if unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "nogit"


def _build_parser() -> argparse.ArgumentParser:
    """Build the smoke-script argument parser.

    ``--pitch-id`` is the only content source (the free-text --premise mode
    retired with the single-shot product — the writer's input is a judged
    StoryPitch; manual topics enter upstream via pitch_angles.py --topic).
    ``--refs`` is required: every character still must be grounded on key-art.
    """
    parser = argparse.ArgumentParser(
        description="End-to-end smoke for the multi-shot pipeline."
    )
    parser.add_argument(
        "--pitch-id",
        type=int,
        required=True,
        help="Approved AnglePitchRecord id; its story_json is the writer's input.",
    )
    parser.add_argument(
        "--refs",
        nargs="+",
        required=True,
        help="Reference key-art image paths that ground every still (>=1).",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Live render + assembly. Prints the credit table first and requires "
        "an interactive 'yes' before any paid call.",
    )
    parser.add_argument(
        "--bgm",
        default=None,
        help="Optional ready-made BGM audio file mixed at 0.2 volume (Sonilo "
        "generation not wired — cost unmeasured, spec §6.4).",
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
        SystemExit: if no row with that id exists — a clear operator error rather
            than an opaque AttributeError downstream.
    """
    pitch = db.get(AnglePitchRecord, pitch_id)
    if pitch is None:
        raise SystemExit(f"No AnglePitchRecord with id={pitch_id} — nothing to render.")
    return pitch


def resolve_pitch(args, db) -> tuple[StoryPitch, int]:
    """Load and re-inflate the approved pitch's full story (the Stage-1 bridge).

    Reads ``story_json`` — the complete StoryPitch the pitcher persisted — and
    validates it back into the typed model. A row with NULL story_json (a
    pre-Stage-B legacy pitch) is a hard error, NOT a fallback to the ``take``
    logline: the logline path silently discarded the beat structure (the exact
    gap the 2026-07-04 redesign closes) and its ``render_backend`` companion
    column is always NULL now, which made every render default to veo3_1.

    Args:
        args: Parsed argparse namespace (uses ``pitch_id``).
        db: An open SQLAlchemy session.

    Returns:
        ``(story_pitch, pitch_id)`` ready for ``ContentWriter.write``.

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
    print(f"[pitch] mode={pitch.mode.value} beats={len(pitch.beats)}\n")
    return pitch, args.pitch_id


def main() -> None:
    """Parse args, run pitch → write → jobs → dry-run cost, print everything."""
    args = _build_parser().parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sha = _git_sha()
    record_path = Path("output/smoke_runs") / f"smoke_{ts}_{sha}.txt"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_file = record_path.open("w", encoding="utf-8")
    record_file.write(f"# smoke_content_writer run\n# timestamp: {ts}\n# git_sha: {sha}\n\n")
    record_file.flush()

    db = SessionLocal()
    original_stdout = sys.stdout
    sys.stdout = _Tee(original_stdout, record_file)

    try:
        pitch, pitch_id = resolve_pitch(args, db)

        rules = RenderRules()
        print("[write] two-call multi-shot writer")
        package = ContentWriter(llm=llm_for_seat("content_writer")).write(
            pitch,
            rules=rules,
            reference_image_paths=list(args.refs),
            pitch_id=pitch_id,
        )

        print("=" * 70)
        print(f"STYLE ANCHOR:  {package.style_anchor}")
        print(f"ANCHORS:       {package.anchors_block}")
        print(f"GROUPS:        {package.consistency_groups}")
        print(f"REFS:          {package.reference_image_paths}")
        for i, shot in enumerate(package.shots):
            print("-" * 70)
            print(
                f"SHOT {i} [{shot.beat_role.value}] {shot.duration_seconds}s "
                f"tag={shot.motion_tag.value} model={shot.model_cli_id}"
            )
            print(f"  STILL:  {shot.still_prompt}")
            print(f"  MOTION: {shot.motion_prompt}")
            if shot.narration_line:
                print(f"  VO:     {shot.narration_line}")
        print("-" * 70)
        print(f"HOOK TEXT:     {package.hook_text}")
        print(f"CAPTION:       {package.caption}")
        print(f"HASHTAGS:      {package.hashtags}")
        if package.music_brief:
            print(f"MUSIC:         {package.music_brief}")
        if package.rationale:
            print(f"RATIONALE:     {package.rationale}")
        print("=" * 70 + "\n")

        jobs = render_jobs(package, rules)
        print(f"[jobs] {len(jobs)} render jobs:")
        for job in jobs:
            covers = job.covers_shots or [job.shot_index]
            print(f"  {job.kind:<10} {job.model_cli_id:<15} shots={covers} duration={job.duration}")

        out_dir = str(Path("output/smoke_runs") / f"render_{ts}_{sha}")
        print("\n[execute] DRY RUN (cost estimate only)")
        estimate = execute(jobs, out_dir, dry_run=True)
        print(f"\n[result] credits_spent estimate: {estimate.credits_spent}")

        if args.real:
            # Explicit confirm between the printed cost table and any paid call
            # (DECISIONS_LOCKED L7 — no silent spends).
            answer = input(
                f"\nSpend ~{estimate.credits_spent} credits on this render? "
                "Type 'yes' to proceed: "
            )
            if answer.strip().lower() != "yes":
                raise SystemExit("Aborted before any paid call — nothing spent.")

            print("\n[execute] REAL RENDER")
            result = execute(jobs, out_dir)
            print(f"  stills: {result.still_paths}")
            for clip in result.clips:
                print(f"  clip shots={clip.shot_indices} audio={clip.has_audio} -> {clip.clip_path}")

            print("\n[assemble] concat + narration + hook card")
            final_path = assemble(
                result,
                package,
                str(Path(out_dir) / "final.mp4"),
                tts=HiggsfieldTTS(),  # ~0.15cr per narration line (measured)
                bgm_path=args.bgm,
            )
            print(f"\n[FINAL] {final_path}")
            print("Post-gate reminder: AIGC label at upload; judge on evie I1/I2 + C1/C2.")

    finally:
        sys.stdout = original_stdout
        record_file.close()
        db.close()
        print(f"\n[record saved] {record_path}")


if __name__ == "__main__":
    main()
