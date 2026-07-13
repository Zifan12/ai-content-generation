"""
End-to-end smoke for the motion-native scene lane (pitch → write → scene job → cost).

Loads an approved AnglePitchRecord's FULL story (story_json → StoryPitch), runs
the two-call writer, composes the ONE scene job (spec 2026-07-06 A3), prints the
COMPOSED SCENE PROMPT plus the takes×rate credit estimate. Reference paths are
REQUIRED and must follow the path convention refs/<character_slug>/... (crash
loud otherwise; grounding is mandatory, DECISIONS_LOCKED L3).

By default runs dry_run (prompt + cost only, ZERO CLI calls, nothing spent).
--real requires an interactive 'yes', renders --takes generations (failed takes
are uncharged and reported), then — single take only — synthesizes narration and
assembles the final mp4. With --takes > 1 assembly is deliberately skipped: the
user picks the best take first (D6 ladder), then re-runs assembly on it.

RETAKE LADDER (D6): --resolution 480p to sanity-test a new prompt → 720p
default single take → 1080p --takes 2-3 for finals.

USAGE:
  uv run python scripts/smoke_content_writer.py --pitch-id 24 --refs refs/will/*.png refs/elfie/*.png
  uv run python scripts/smoke_content_writer.py --pitch-id 24 --refs ... --real --takes 2
  uv run python scripts/smoke_content_writer.py --pitch-id 24 --refs ... --real --resolution 1080p --takes 3

OUTPUT:
  Prints the full MultiShotPackage, the composed scene prompt, and the credit
  estimate; in --real mode also per-take clip paths (and final.mp4 when a single
  take assembles). A timestamped transcript is saved to output/smoke_runs/, plus
  a machine-readable JSON dump of the FULL flow at the same path with a .json
  extension.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Repo root on sys.path — scripts run as files, not as a package (same pattern
# as scripts/label.py; previously this script was invoked with PYTHONPATH set).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv("config/.env")

# Windows console defaults to cp1252; LLM-written captions/prompts carry emoji
# and typographic unicode, which crashed the Tee'd print mid-run (BUG-011 sibling,
# 2026-07-05). Replace rather than crash — the utf-8 record file keeps the real text.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from src.database import SessionLocal  # noqa: E402
from src.generation.assembly import assemble  # noqa: E402
from src.generation.content_writer import ContentWriter  # noqa: E402
from src.generation.reference_check import (  # noqa: E402
    check_references,
    render_manifest,
)
from src.generation.executor import execute_scene  # noqa: E402
from src.generation.prompt_translation import translate_job  # noqa: E402
from src.providers.tts.higgsfield_tts import HiggsfieldTTS  # noqa: E402
from src.generation.render_adapters.adapter import render_jobs  # noqa: E402
from src.generation.render_adapters.rules import RenderRules  # noqa: E402
from src.models.angle_pitch import AnglePitchRecord  # noqa: E402
from src.models.trending_event import TrendingEventRecord  # noqa: E402, F401  (registers the FK target table for commit-time table sort)
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
        "--location",
        default=None,
        help="Location slug under refs/_location/<slug>/ (room image + "
        "world_anchor.txt). Grounds the setting to canon; omit for an "
        "ungrounded render.",
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
    parser.add_argument(
        "--takes",
        type=int,
        default=1,
        help="Independent scene generations to render (D6 ladder: 1 for dev, "
        "2-3 at 1080p for finals; user picks the best take).",
    )
    parser.add_argument(
        "--resolution",
        default=None,
        help="Override the yaml scene_lane default (480p/720p/1080p/4k). "
        "480p = cheapest sanity pass for a brand-new prompt.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help="Override the yaml scene_lane default seconds (CLI cap 15, "
        "measured 2026-07-06). 6-beat pitches breathe better at 15.",
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


def load_location(slug: str) -> tuple[list[str], str]:
    """Resolve a location slug to (image_paths, world_anchor_text).

    Reads refs/_location/<slug>/: every image file (png/jpg/jpeg, sorted by
    filename) is a location reference; world_anchor.txt (utf-8) is the cached
    setting description. Exits loudly if the folder, an image, or the text file
    is missing — a mistyped slug should fail before any paid render, not
    silently ground nothing.

    Args:
        slug: Folder name under refs/_location/ (e.g. "elfie_bedroom").

    Returns:
        (image_paths, world_anchor_text) ready to pass to ContentWriter.write.

    Raises:
        SystemExit: if the folder is absent, holds no image, or lacks
            world_anchor.txt.
    """
    folder = Path("refs/_location") / slug
    if not folder.is_dir():
        raise SystemExit(f"No location folder refs/_location/{slug} — check the slug.")
    images = sorted(
        str(p) for p in folder.iterdir()
        if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
    if not images:
        raise SystemExit(f"No image files in refs/_location/{slug} — need a room screencap.")
    anchor_file = folder / "world_anchor.txt"
    if not anchor_file.is_file():
        raise SystemExit(f"No world_anchor.txt in refs/_location/{slug} — generate it first.")
    return images, anchor_file.read_text(encoding="utf-8").strip()


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

    json_path = record_path.with_suffix(".json")
    # Provenance dump of the FULL flow, written/refreshed at each stage boundary
    # so a crash mid-run still leaves everything computed so far on disk.
    flow: dict = {
        "meta": {
            "timestamp": ts,
            "git_sha": sha,
            "pitch_id": args.pitch_id,
            "location": args.location,
            "real": bool(args.real),
            "bgm": args.bgm,
        }
    }

    def _dump_flow() -> None:
        json_path.write_text(
            json.dumps(flow, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    try:
        pitch, pitch_id = resolve_pitch(args, db)
        flow["story_pitch"] = pitch.model_dump(mode="json")
        _dump_flow()

        # Resolve the effective location: --location overrides the pitch's stored
        # tag and BACKFILLS it (a late tag is remembered next time). Otherwise the
        # pitch's own location_slug (set at approval) drives grounding.
        record = load_pitch(db, pitch_id)
        if args.location and args.location != record.location_slug:
            record.location_slug = args.location
            db.commit()
            print(f"[location] backfilled pitch #{pitch_id} -> {args.location!r}")
        location_slug = args.location or record.location_slug

        # Reference gate: derive required refs from the pitch, verify the shared
        # library, HALT before any spend if anything is missing (spec 2026-07-11).
        manifest = check_references(pitch, location_slug)
        print(render_manifest(manifest))
        if not manifest.ready:
            raise SystemExit("Reference check failed — nothing spent.")

        world_anchor = ""
        if location_slug:
            _images, world_anchor = load_location(location_slug)

        rules = RenderRules()
        print("[write] two-call multi-shot writer")
        package = ContentWriter(llm=llm_for_seat("content_writer")).write(
            pitch,
            rules=rules,
            reference_image_paths=manifest.character_reference_paths,
            pitch_id=pitch_id,
            world_anchor=world_anchor,
            location_reference_paths=manifest.location_reference_paths,
        )

        # TEMP (pitch 24 manual render): the blind text-only writer wrote
        # ref-conflicting identities (swapped Will/Zeo hair, wrong Elfie costume).
        # Override anchors_block to match the supplied Wistoria key-art so the
        # multi-character stills label each ref correctly. Remove once the writer
        # gets ref-accurate anchors (vision describe-step). See render_taste_test/
        # wistoria_refs/.
        if pitch_id == 24:
            package.anchors_block = (
                "Will has teal-blue messy hair with one upward strand, round "
                "glasses, violet eyes, a dark caped uniform with gold epaulettes. "
                "Elfie has long ice-blue hair, blue eyes, a white-and-gold "
                "off-shoulder dress with a blue chest gem. "
                "Zeo has spiky white-silver hair, tan skin, teal eyes, a "
                "sleeveless white vest and grey cloak."
            )
            print("[TEMP] pitch 24: anchors_block overridden to match refs")

        print("=" * 70)
        print(f"STYLE ANCHOR:  {package.style_anchor}")
        print(f"ANCHORS:       {package.anchors_block}")
        print(f"REFS:          {package.reference_image_paths}")
        if package.location_reference_paths:
            print(f"LOCATION REFS: {package.location_reference_paths}")
            print(f"WORLD ANCHOR:  {package.world_anchor}")
        for i, shot in enumerate(package.shots):
            print("-" * 70)
            print(
                f"SHOT {i} [{shot.beat_role.value}] {shot.duration_seconds}s "
                f"tag={shot.motion_tag.value} model={shot.model_cli_id}"
            )
            print(f"  SCENE:  {shot.scene_line}")
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

        flow["package"] = package.model_dump(mode="json")
        _dump_flow()

        jobs = render_jobs(package, rules)
        # D-language (spec 2026-07-13): translate the composed scene prompt
        # EN->ZH when the model's dialect leaf asks for it. Runs on dry runs
        # too, so the Chinese prompt is inspectable BEFORE any spend; a failed
        # mechanical check falls back to the English prompt loudly
        # (job.translation_status carries the outcome into the JSON dump).
        if rules.model(rules.scene_model())["dialect"].get("prompt_language") == "zh":
            print("[translate] prompt_language=zh -> prompt_translator seat")
            dialogue_lines = [
                shot.dialogue_line for shot in package.shots if shot.dialogue_line
            ]
            translator = llm_for_seat("prompt_translator")
            jobs = [translate_job(job, dialogue_lines, rules, translator) for job in jobs]
            for job in jobs:
                print(f"[translate] status={job.translation_status}")
        flow["render_jobs"] = [job.model_dump(mode="json") for job in jobs]
        _dump_flow()
        scene_job = jobs[0]  # scene lane: exactly ONE composed multi_shot job (A3/D3)
        print("[scene job] composed prompt " + "=" * 46)
        print(scene_job.prompt)
        print("=" * 70)
        print(
            f"[scene job] model={scene_job.model_cli_id} shots={scene_job.covers_shots} "
            f"duration={scene_job.duration}s refs={len(scene_job.reference_images)} "
            f"prompt_chars={len(scene_job.prompt)}"
        )

        out_dir = str(Path("output/smoke_runs") / f"render_{ts}_{sha}")
        print("\n[execute] DRY RUN (yaml-rate estimate, zero CLI calls)")
        estimate = execute_scene(
            scene_job, out_dir,
            takes=args.takes, duration=args.duration, resolution=args.resolution,
            dry_run=True, rules=rules,
        )
        print(f"\n[result] credits_spent estimate: {estimate.credits_spent}")
        flow["cost_estimate"] = {
            "credits_total": estimate.credits_spent,
            "takes": args.takes,
            "resolution": args.resolution,
            "out_dir": out_dir,
        }
        _dump_flow()

        if args.real:
            # Explicit confirm between the printed cost estimate and any paid
            # call (DECISIONS_LOCKED L7 — no silent spends).
            answer = input(
                f"\nSpend ~{estimate.credits_spent} credits on {args.takes} take(s)? "
                "Type 'yes' to proceed: "
            )
            if answer.strip().lower() != "yes":
                raise SystemExit("Aborted before any paid call — nothing spent.")

            print("\n[execute] REAL RENDER")
            result = execute_scene(
                scene_job, out_dir,
                takes=args.takes, duration=args.duration, resolution=args.resolution,
                rules=rules,
            )
            for clip in result.clips:
                print(f"  take shots={clip.shot_indices} audio={clip.has_audio} -> {clip.clip_path}")
            flow["render_result"] = result.model_dump(mode="json")
            _dump_flow()

            if len(result.clips) == 1:
                print("\n[assemble] narration + hook card + tail-fade")
                final_path = assemble(
                    result,
                    package,
                    str(Path(out_dir) / "final.mp4"),
                    tts=HiggsfieldTTS(),  # ~0.15cr per narration line (measured)
                    bgm_path=args.bgm,
                )
                print(f"\n[FINAL] {final_path}")
                print("Post-gate reminder: AIGC label at upload; judge on evie I1/I2 + C1/C2.")
                flow["final_video"] = final_path
                _dump_flow()
            else:
                print(
                    f"\n[assemble] skipped — {len(result.clips)} takes rendered; pick "
                    "the best (D6), then assemble it (re-run --takes 1 resumes from "
                    "the manifest, or assemble manually)."
                )

    finally:
        sys.stdout = original_stdout
        record_file.close()
        db.close()
        print(f"\n[record saved] {record_path}")
        if json_path.exists():
            print(f"[flow json saved] {json_path}")


if __name__ == "__main__":
    main()
