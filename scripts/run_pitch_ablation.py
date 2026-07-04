"""
Ablation: does the mode-playbook's worked example anchor the StoryPitcher into
generic pitches?

Controlled experiment. For each fixture (event, gap), run the pitcher TWICE on
the SAME gap — arm A with the playbook worked example present (production
default), arm B with it stripped (`_format_playbook(include_example=False)`
reassigned onto a throwaway pitcher). Everything else is held fixed, so the
single changed variable is the worked example. Score every produced pitch with
the GroundednessJudge and compare the arms on all-pass / check-pass / swap-fail.
If arm B is more grounded, the worked example was the anchor — bug confirmed,
generation-side.

Metrics persist to eval_runs tagged by git SHA (mirrors run_self_agreement.py).

LIVE SPEND: calls the real pitcher twice per fixture event plus the judge per
pitch. State the cost ceiling before running.
"""

import argparse
import json
import logging
import subprocess
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

from src.database import SessionLocal  # noqa: E402
from src.evals.groundedness_check import GroundednessJudge  # noqa: E402
from src.models.eval import EvalRun  # noqa: E402
from src.monitor.schemas import GapAnalysis, TrendingEvent  # noqa: E402
from src.monitor.story_pitcher import StoryPitcher, _format_playbook  # noqa: E402
from src.providers.llm.factory import llm_for_seat  # noqa: E402
from src.rag.embedder import BgeM3Embedder  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "data" / "golden" / "pitcher_groundedness_fixture_v1.json"
COMPONENT = "story-pitcher-groundedness-ablation"


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
    CLI entrypoint for the StoryPitcher groundedness ablation.

    Loads the fixture, runs each (event, gap) through both playbook arms, scores
    every pitch with the GroundednessJudge, aggregates per-arm groundedness
    stats, and persists one EvalRun row per metric tagged with the git SHA.
    """
    parser = argparse.ArgumentParser(description="Run StoryPitcher groundedness ablation.")
    parser.add_argument("--fixture", type=Path, default=FIXTURE_PATH)
    parser.add_argument("--limit", type=int, default=None, help="cap number of fixture events (cost control)")
    parser.add_argument("--dataset-version", default="v1")
    args = parser.parse_args()

    judge = GroundednessJudge(llm=llm_for_seat("groundedness_judge"))
    db = SessionLocal()
    
    try:
        # --- BLOCK 1: load the fixture --------------------------------------
        # Rebuild (TrendingEvent, GapAnalysis) pairs from the Task 1 fixture.
        # Event metadata beyond the four persisted fields is synthesized — the
        # fixture is a scoring input, not a live scrape.
        pairs: list[tuple[TrendingEvent, GapAnalysis]] = []
        raw_entries = json.loads(args.fixture.read_text())[:args.limit]
        
        for entry in raw_entries:
            event = TrendingEvent.model_validate({
                **{k: entry[k] for k in ("headline", "reaction_sample",
                                      "trendiness_score", "virality_window_hours")},

                "subreddit": "",
                "url": "",
                "raw_source_data": {},
                "origin": "manual",
            })
            gap = GapAnalysis.model_validate(entry["gap"])
            pairs.append((event, gap))

        if not pairs:
            log.error("No fixture pairs loaded from %s", args.fixture)
            raise SystemExit(1)
        log.info("Ablation over %d fixture events (2 arms each)", len(pairs))

        # --- BLOCK 2: run both arms, score every pitch ----------------------
        # One embedder shared by both pitchers — loading BgeM3 twice would just
        # double GPU VRAM, and the diversity check it feeds is identical per arm.
        # Build pitchers once outside the loop (reuse across pairs is safe).
        # Arm A keeps the production playbook; arm B strips ONLY the worked
        # example — the single changed variable.
        verdicts_a: list = []
        verdicts_b: list = []

        embedder = BgeM3Embedder()
        pitcher_a = StoryPitcher(llm=llm_for_seat("story_pitcher"), embedder=embedder)
        pitcher_b = StoryPitcher(llm=llm_for_seat("story_pitcher"), embedder=embedder)
        pitcher_b.playbook_block = _format_playbook(include_example=False)

        for event, gap in pairs:
            # Per-event isolation (mirrors run_self_agreement.py): a failed
            # pitch/judge (validator reject, truncation, transient API error)
            # drops THIS event and keeps verdicts already paid for. Both arms
            # are scored inside the SAME try so a partial failure drops the
            # event from BOTH arms — the ablation stays paired per event.
            try:
                slate_a = pitcher_a.pitch(event, gap)
                slate_b = pitcher_b.pitch(event, gap)
                a = [judge.judge(gap, pitch) for pitch in slate_a.pitches]
                b = [judge.judge(gap, pitch) for pitch in slate_b.pitches]
            except Exception as e:
                log.warning("Skipped event %r: %s", event.headline, e)
                continue
            verdicts_a.extend(a)
            verdicts_b.extend(b)

        if not verdicts_a and not verdicts_b:
            log.error("No successful pitches — every event failed")
            raise SystemExit(1)

        # --- BLOCK 3: aggregate into metrics ---------------------------------
        # A StoryPitch renders evidence into shootable prose beats, never a
        # verbatim quote, so "paraphrased" is the EXPECTED on-target label — it
        # counts as USING the evidence. Only "absent" is a real miss. (Counting
        # strictly "grounded" would floor both arms and could invert the result
        # — the binary collapse the 3-value label exists to avoid.)
        #   all_pass  : fraction of pitches where NO evidence_item is absent
        #   check_pass: micro-avg — (grounded + paraphrased) / total items
        #   swap_fail : fraction of pitches judged generic (swap == True)
        # Hypothesis: if the worked example anchors the pitcher into generic
        # pitches, arm B (example stripped) should show LOWER swap_fail and
        # HIGHER all_pass / check_pass than arm A.
        used_labels = {"grounded", "paraphrased"}

        def _arm_metrics(verdicts: list, suffix: str) -> dict[str, float]:
            # verdicts is guaranteed non-empty here: the per-event try scores
            # both arms together, so verdicts_a/_b are empty or non-empty in
            # lockstep, and the both-empty case already exited above.
            n = len(verdicts)
            all_pass = sum(
                1 for v in verdicts
                if v.evidence_items
                and all(it.label in used_labels for it in v.evidence_items)
            ) / n
            total_items = sum(len(v.evidence_items) for v in verdicts)
            used_items = sum(
                1 for v in verdicts for it in v.evidence_items
                if it.label in used_labels
            )
            check_pass = used_items / total_items if total_items else 0.0
            swap_fail = sum(1 for v in verdicts if v.swap) / n
            return {
                f"all_pass_{suffix}": all_pass,
                f"check_pass_{suffix}": check_pass,
                f"swap_fail_{suffix}": swap_fail,
            }

        metrics: dict[str, float] = {}
        metrics.update(_arm_metrics(verdicts_a, "A"))
        metrics.update(_arm_metrics(verdicts_b, "B"))

        sha = git_sha()
        for name, value in metrics.items():
            db.add(EvalRun(
                component=COMPONENT,
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
