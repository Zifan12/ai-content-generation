import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from src.evals.harness import EvalHarness, EvalReport


FAKE_LABELS = [
    {"id": 1, "views": 600000, "likes": 30000, "comments": 5000, "shares": 3000,
     "virality_class": "viral", "weighted_er": 5.0},
    {"id": 2, "views": 10000, "likes": 100, "comments": 10, "shares": 5,
     "virality_class": "flop", "weighted_er": 0.15},
    {"id": 3, "views": 80000, "likes": 2000, "comments": 500, "shares": 200,
     "virality_class": "mid", "weighted_er": 3.5},
    {"id": 4, "views": 700000, "likes": 100, "comments": 50, "shares": 10,
     "virality_class": "suspicious", "weighted_er": 0.07},
]


def fake_scorer(item: dict) -> float:
    """Mimics a perfect scorer: returns 1.0 for viral, 0.0 for rest."""
    return 1.0 if item["virality_class"] == "viral" else 0.0


@pytest.fixture
def tmp_jsonl(tmp_path):
    path = tmp_path / "labels.jsonl"
    with open(path, "w") as f:
        for item in FAKE_LABELS:
            f.write(json.dumps(item) + "\n")
    return path


def test_harness_run_returns_report(tmp_jsonl):
    mock_db = MagicMock()
    harness = EvalHarness(golden_path=tmp_jsonl, db=mock_db)
    harness.register("fake-scorer", fake_scorer)

    report = harness.run(component="fake-scorer")

    assert isinstance(report, EvalReport)
    assert report.component == "fake-scorer"
    assert "auc" in report.metrics
    assert "precision_at_10" in report.metrics
    assert report.metrics["auc"] == pytest.approx(1.0)


def test_harness_writes_eval_runs(tmp_jsonl):
    mock_db = MagicMock()
    harness = EvalHarness(golden_path=tmp_jsonl, db=mock_db)
    harness.register("fake-scorer", fake_scorer)

    harness.run(component="fake-scorer")

    assert mock_db.add.called
    assert mock_db.commit.called


def test_harness_raises_on_unknown_component(tmp_jsonl):
    mock_db = MagicMock()
    harness = EvalHarness(golden_path=tmp_jsonl, db=mock_db)

    with pytest.raises(KeyError):
        harness.run(component="nonexistent")
