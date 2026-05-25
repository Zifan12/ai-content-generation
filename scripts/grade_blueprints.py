"""Human-grade Blueprint extractions and record scores to EvalRun.

PIPELINE ROLE:
  BlueprintRecords → Human review (this file) → EvalRun metrics

WHY THIS SCRIPT EXISTS:
  P1.5 Foundation needs ground truth for eval gates. This script randomly
  samples Blueprints, shows them to human annotator with 1-5 rubric, records
  scores to EvalRun table. CI gate: avg_score >= 3.5 to unblock next phase.

WORKFLOW:
  1. Sample N random Blueprints (default: 20) at specified extractor_version
  2. For each Blueprint:
     - Load Transcript text
     - Show video stats + transcript + extracted Blueprint
     - Prompt human for score (1-5) on rubric
  3. Compute mean score
  4. Record to EvalRun: (component="blueprint-grader", metric_name="mean_score",
     metric_value=<mean>, git_sha=<current>, dataset_version=<arg>)
  5. Output results

RUBRIC (1-5):
  5: Perfect extraction, format/hook/payoff match, mechanics calibrated
  4: Good, minor mechanic disagreement
  3: OK, one enum off or miscalibrated
  2: Bad, multiple enums off or wildly wrong
  1: Useless, barely related to video

FLAGS:
  --sample N                    Blueprints to grade (default: 20, ~30 min)
  --extractor-version VERSION   Which extractor schema (default: current in schema.py)
  --dataset-version VERSION     For EvalRun tracking (default: v1)

TIMING:
  ~1-2 minutes per Blueprint (human review). 20 Blueprints ≈ 30-40 minutes.

"""
import argparse
import json
import logging
import subprocess
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.models.blueprint import BlueprintRecord
from src.models.eval import EvalRun
from src.models.transcript import Transcript
from src.models.trend import RawContentItem
from src.blueprints.schema import EXTRACTOR_VERSION

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


RUBRIC = """
Score the Blueprint extraction 1-5 holistically:
  5 — Perfect: format/hook/payoff dead-on, mechanic floats feel right, structure makes sense.
  4 — Good: minor mechanic disagreement (~0.1) but enums all reasonable.
  3 — OK: one enum off OR multiple mechanics noticeably miscalibrated.
  2 — Bad: multiple enums off OR wildly wrong mechanic scores.
  1 — Useless: extraction barely related to the actual video.
""".strip()


def git_sha() -> str:
    """
    Get current short git SHA for audit trail.
    
    Returns: 7-character commit hash (e.g., "a1b2c3d")
             or "unknown" if git is unavailable.
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def get_transcript_text(db: Session, content_item_id: int) -> str | None:
    t = db.scalar(select(Transcript).where(Transcript.content_item_id == content_item_id))
    return t.text if t else None


def main() -> None:
    """
    CLI entry point. Parse args, load Blueprints, grade interactively.
    """
    parser = argparse.ArgumentParser(description="Human-grade Blueprint extractions.")
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--extractor-version", default=EXTRACTOR_VERSION)
    parser.add_argument("--dataset-version", default="v1")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        records = list(
            db.scalars(
                select(BlueprintRecord)
                .where(BlueprintRecord.extractor_version == args.extractor_version)
                .limit(args.sample)
            ).all()
        )
        if len(records) < args.sample:
            log.warning("Only %d records available (asked for %d)", len(records), args.sample)
        if not records:
            raise SystemExit("No blueprint records to grade.")

        print(RUBRIC)
        scores: list[int] = []

        for i, record in enumerate(records, start=1):
            item = db.get(RawContentItem, record.content_item_id)
            transcript = get_transcript_text(db, record.content_item_id)
            print("\n" + "=" * 70)
            print(f"[{i}/{len(records)}] item_id={item.id}")
            print(f"URL: {item.url}")
            print(f"Author: @{item.author_username}")
            print(f"Caption: {item.description}")
            if transcript:
                print(f"Transcript: {transcript[:300]}{'...' if len(transcript) > 300 else ''}")
            print("\nBlueprint:")
            print(json.dumps(record.blueprint_data, indent=2))
            print("\nScore (1-5, or 's' to skip): ", end="", flush=True)

            while True:
                raw = input().strip().lower()
                if raw == "s":
                    print("skipping")
                    break
                try:
                    score = int(raw)
                except ValueError:
                    print("Enter 1-5 or 's': ", end="", flush=True)
                    continue
                if 1 <= score <= 5:
                    scores.append(score)
                    break
                print("Out of range. Enter 1-5 or 's': ", end="", flush=True)

        if not scores:
            print("No scores entered. Aborting.")
            return

        avg = mean(scores)
        print(f"\n=== {len(scores)} grades, avg {avg:.2f} ===")

        sha = git_sha()
        db.add(EvalRun(
            component="blueprint-extractor-v1",
            git_sha=sha,
            metric_name="human_grade_avg",
            metric_value=avg,
            dataset_version=args.dataset_version,
        ))
        db.add(EvalRun(
            component="blueprint-extractor-v1",
            git_sha=sha,
            metric_name="human_grade_count",
            metric_value=float(len(scores)),
            dataset_version=args.dataset_version,
        ))
        db.commit()
        print(f"Written to eval_runs (git_sha={sha}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
