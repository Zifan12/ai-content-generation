import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from src.evals.metrics import auc, precision_at_k
from src.models.eval import EvalRun

@dataclass
class EvalReport:
    component: str # which scorer ran
    metrics: dict[str, float] # {"auc": 0.82, "precision_at_10": 0.6}
    git_sha: str # which commit produced this result
    dataset_version: str # which golden set version, e.g. "v1"

class EvalHarness:
    def __init__(self, golden_path: Path = Path("data/golden/labels.jsonl"), db=None, dataset_version: str = "v1"):
        self.golden_path = golden_path
        self.db = db
        self.dataset_version = dataset_version
        self._scorers: dict[str, Callable[[dict], float]] = {}

    def register(self, name: str, scorer: Callable[[dict], float]) -> None:
        self._scorers[name] = scorer

    def run(self, component: str) -> EvalReport:
        if component not in self._scorers:
            raise KeyError(f"No scorer registered for '{component}'. Call register() first.")

        scorer = self._scorers[component]
        items = self._load_golden()
        git_sha = self._git_sha()

        y_true, y_score = [], []

        for item in items:
            y_true.append(1 if item["virality_class"] == "viral" else 0)
            y_score.append(scorer(item)) # NOTE: scorer is a function 

        metrics = {}
        try:
            metrics["auc"] = auc(y_true, y_score)
        except ValueError:
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
        with open(self.golden_path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
        
    def _git_sha(self) -> str:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], text=True
            ).strip()
        except Exception:
            return "unknown"
        
    def _persist(self, component: str, git_sha: str, metrics: dict[str, float]) -> None:
        for metric_name, metric_value in metrics.items():
            self.db.add(EvalRun(
                component=component,
                git_sha=git_sha,
                metric_name=metric_name,
                metric_value=metric_value,
                dataset_version=self.dataset_version,
            ))
        self.db.commit()