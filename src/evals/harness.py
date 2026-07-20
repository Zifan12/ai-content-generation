"""
Eval harness CLI and registry.

Single entry point for scoring registered components against the golden set.
Persists every metric to `eval_runs` keyed by git SHA so regressions across
commits are auditable; without this loop, prompt/code changes ship blind.
"""

import argparse
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import select

from src.analysis.scorer import RuleBasedScorer
from src.database import SessionLocal
from src.evals.metrics import auc, precision_at_k
from src.models.eval import EvalRun

@dataclass
class EvalReport:
    """
    Result of one EvalHarness.run — metrics + reproducibility tags.
    """

    component: str
    metrics: dict[str, float]
    git_sha: str
    dataset_version: str

class EvalHarness:
    """
    Register scorers, run against golden set, persist EvalRun rows.
    """

    def __init__(self, golden_path: Path = Path("data/golden/labels.jsonl"), db=None, dataset_version: str = "v1"):
        self.golden_path = golden_path
        self.db = db
        self.dataset_version = dataset_version
        self._scorers: dict[str, Callable[[dict], float]] = {}

    def register(self, name: str, scorer: Callable[[dict], float]) -> None:
        """
        Bind a scorer callable to a component name for later run() calls.
        """
        self._scorers[name] = scorer

    def run(self, component: str) -> EvalReport:
        """
        Score golden set with registered scorer; persist to DB if db is set.

        Returns EvalReport with AUC and precision@10.
        Raises KeyError if component has no registered scorer.
        """
        if component not in self._scorers:
            raise KeyError(f"No scorer registered for '{component}'. Call register() first.")

        scorer = self._scorers[component]
        items = self._load_golden()
        git_sha = self._git_sha()

        y_true, y_score = [], []

        for item in items:
            # Binary AUC: only "viral" = positive; mid/flop/suspicious all negative.
            y_true.append(1 if item["virality_class"] == "viral" else 0)
            y_score.append(scorer(item))

        metrics = {}
        try:
            metrics["auc"] = auc(y_true, y_score)
        except ValueError:
            # AUC undefined when golden set has only one class; report NaN rather than crash.
            metrics["auc"] = float("nan")
        metrics["precision_at_10"] = precision_at_k(y_true, y_score, 10)

        if self.db is not None:
            self._persist(component, git_sha, metrics)
        
        return EvalReport(
            component=component,
            metrics=metrics,
            git_sha=git_sha,
            dataset_version=self.dataset_version,
        )
     

    def _load_golden(self) -> list[dict]:
        """
        Load golden label records from JSONL; blank lines silently skipped.
        """
        with open(self.golden_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
        
    def _git_sha(self) -> str:
        """
        Return short HEAD SHA; falls back to 'unknown' outside git repos.
        """
        # subprocess fails outside a git repo (CI containers, bare checkouts); fall back
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], text=True
            ).strip()
        except Exception:
            return "unknown"
        
    def _persist(self, component: str, git_sha: str, metrics: dict[str, float]) -> None:
        """
        Write one EvalRun row per metric and commit.
        """
        for metric_name, metric_value in metrics.items():
            self.db.add(EvalRun(
                component=component,
                git_sha=git_sha,
                metric_name=metric_name,
                metric_value=metric_value,
                dataset_version=self.dataset_version,
            ))
        self.db.commit()

def main():
    """
    CLI entrypoint. Supported --component values: rule-based-scorer.

    The blueprint-extractor-v1 component was removed with the Blueprint corpus lane
    (ADR-0009); its schema_valid_rate gate no longer has an extractor to measure.
    """
    parser = argparse.ArgumentParser(description="Run eval harness against golden set.")
    parser.add_argument("--component", required=True, help="Scorer name to evaluate")
    parser.add_argument("--dataset-version", default="v1")
    args = parser.parse_args()

    db = SessionLocal()

    try:
        harness = EvalHarness(dataset_version=args.dataset_version, db=db)

        if args.component == "rule-based-scorer":
            rule_scorer = RuleBasedScorer()
            harness.register(
                "rule-based-scorer",
                lambda item: rule_scorer.score(
                    views=item["views"],
                    likes=item["likes"],
                    comments=item["comments"],
                    shares=item["shares"],
                ).score,
                
            )
        else:
            raise SystemExit(f"Unknown component: {args.component}. Supported: rule-based-scorer")
        
        report = harness.run(component=args.component)
        print(
            json.dumps({
                "component": report.component,
                "metrics": report.metrics,
                "git_sha": report.git_sha,
                "dataset_version": report.dataset_version,
                }, indent=2
            )
        )

    finally:
        db.close()



if __name__ == "__main__":
    main()

