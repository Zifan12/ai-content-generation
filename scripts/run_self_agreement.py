"""
Measure Blueprint extractor self-agreement.

The extractor is LLM-backed and non-deterministic, so two calls on the same
item can disagree. This script quantifies that disagreement: Cohen's kappa
on enum fields and MAE on mechanic floats, persisted to eval_runs tagged by
git SHA. Used to detect regressions when the extractor prompt or model
changes — without it, prompt edits can silently degrade every downstream
consumer (RAG conditioning, ML features, generation).
"""

import argparse
import logging
import subprocess

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.blueprints.extractor import BlueprintExtractor
from src.blueprints.schema import EXTRACTOR_VERSION
from src.database import SessionLocal
from src.evals.blueprint_eval import ENUM_FIELDS, MECHANIC_FIELDS, cohen_kappa_pairs, mae_pairs
from src.models.eval import EvalRun
from src.models.transcript import Transcript
from src.models.trend import RawContentItem

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

def get_transcript_text(db: Session, content_item_id: int) -> str | None:
    """Return plain transcript text for a content item, or None if no Transcript row exists."""
    stmt = (
        select(Transcript.text)
        .where(Transcript.content_item_id == content_item_id)
    )
    return db.scalar(stmt)

def git_sha() -> str:
    """
    Return short git SHA of HEAD, or "unknown" if git unavailable or call fails.
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"

def main():
    """
    CLI entrypoint for blueprint extractor self-agreement eval.

    Extracts each sampled item twice, computes Cohen's kappa per enum field
    and MAE per mechanic field across the two runs, and persists one EvalRun
    row per metric tagged with the current git SHA and dataset version.
    """
    parser = argparse.ArgumentParser(description="Run blueprint self-agreement eval.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dataset-version", default="v1")
    args = parser.parse_args()

    extractor = BlueprintExtractor()
    db = SessionLocal()

    try:
        items = list(
            db.scalars(
                select(RawContentItem)
                .where(RawContentItem.description.is_not(None))
                .limit(args.limit)
            ).all()
        )
        log.info("Self-agreement over %d items", len(items))

        run_a = []
        run_b = []
        for item in items:
            try:
                text = get_transcript_text(db, item.id)
                # Two independent extractions per item; non-determinism between runs is the self-agreement signal.
                run_a.append(extractor.extract(item=item, transcript_text=text))
                run_b.append(extractor.extract(item=item, transcript_text=text))

            except Exception as e:
                log.warning("Skipped item %d: %s", item.id, e)
                continue

        if not run_a:
            log.error("No successful pairs — all extractions failed")
            raise SystemExit(1)
        
        sha = git_sha()
        metrics: dict[str, float] = {}
        
        for field in ENUM_FIELDS:
            a_vals = [getattr(bp, field) for bp in run_a]
            b_vals = [getattr(bp, field) for bp in run_b]
            metrics[f"kappa_{field}"] = cohen_kappa_pairs(a_vals, b_vals)

        for field in MECHANIC_FIELDS:
            a_vals = [getattr(bp, field) for bp in run_a]
            b_vals = [getattr(bp, field) for bp in run_b]
            metrics[f"mae_{field}"] = mae_pairs(a_vals, b_vals)


        mae_values = [v for k, v in metrics.items() if k.startswith("mae_")]
        mae_mean = sum(mae_values)/len(mae_values)
        metrics["mae_mean"] = mae_mean
        metrics["pair_count"] = float(len(run_a))

        for name, value in metrics.items():
            db.add(EvalRun(
                component="blueprint-extractor-v1",
                git_sha=sha,
                metric_name=name,
                metric_value=value,
                dataset_version=args.dataset_version,
            ))
        db.commit()

        log.info("=" * 60)
        for name, value in metrics.items():
            log.info("  %s: %.4f", name, value)

    finally:
        db.close()

if __name__ == "__main__":
    main()