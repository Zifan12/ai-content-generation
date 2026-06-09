"""
Unit tests for the v1 writer-judge verdict schema (src/evals/writer_judge.py).

Covers the typed-verdict contract: DimensionScore must reject any score outside
the 1-5 Likert range, and PackageVerdict must hold a list of per-dimension
scores. No LLM is involved — these are pure schema/validation tests.

NOTE on de-confounding: every out-of-range test supplies VALID `dimension` and
`reason` values, so the ONLY thing that can raise ValidationError is the score
bound itself. A test that omitted those required fields would raise for the
wrong reason (missing fields) and would still "pass" even if the 1-5 constraint
were deleted — a hollow green.
"""

import pytest
from pydantic import ValidationError

from src.evals.writer_judge import DimensionScore, PackageVerdict
from src.evals.package_view import render_for_judge
from tests.test_rubric_checks import baseline_package
 

def test_valid_score_constructs():
    """A score within 1-5, with all required fields present, builds cleanly."""
    ds = DimensionScore(dimension="vividness", score=3, reason="ok")
    assert ds.score == 3


@pytest.mark.parametrize("bad_score", [6, 0, -1, 100])
def test_rejects_out_of_range_score(bad_score):
    """
    A score outside 1-5 raises ValidationError. `dimension` and `reason` are
    supplied so the bound is the ONLY possible cause of the failure — this is
    what makes the green meaningful rather than hollow.
    """
    with pytest.raises(ValidationError):
        DimensionScore(dimension="vividness", score=bad_score, reason="ok")


def test_package_verdict_holds_dimension_scores():
    """
    PackageVerdict is a SIBLING of DimensionScore (both BaseModel) that CONTAINS
    a list of them — the has-a relationship, not is-a. It does not have its own
    `score`; it holds several DimensionScores.
    """
    verdict = PackageVerdict(
        scores=[
            DimensionScore(dimension="vividness", score=4, reason="specific prose"),
            DimensionScore(dimension="convergence", score=2, reason="beats disconnected"),
        ]
    )
    assert len(verdict.scores) == 2
    assert verdict.scores[0].dimension == "vividness"
    

def test_render_for_judge_includes_premise_and_shots():
    package = baseline_package()
    premise = "HYDRA"
    render_text = render_for_judge(premise, package)

    assert "HYDRA" in render_text
    assert package.organizing_principle in render_text
    assert all(s.start_keyframe in render_text for s in package.shots)