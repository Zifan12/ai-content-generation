"""
Unit tests for the v1 writer-judge verdict schema (src/evals/writer_judge.py) and
the package->text renderer (src/evals/package_view.py).

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
from src.evals.rubric_eval import judge_scorecard, device_distribution

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
    

def _fake_verdicts() -> list[PackageVerdict]:
    """
    Three hand-built verdicts with predictable scores, for testing the
    judge_scorecard aggregation without an LLM.

    vividness scores across the three verdicts are 2, 4, 3  -> mean 3.0
    development scores are 5, 5, 5                           -> mean 5.0
    The vividness=2 in the first verdict is the planted failure (<= 2).
    """
    return [
        PackageVerdict(
            scores=[
                DimensionScore(dimension="vividness", score=2, reason="generic prose"),
                DimensionScore(dimension="development", score=5, reason="take advances"),
            ]
        ),
        PackageVerdict(
            scores=[
                DimensionScore(dimension="vividness", score=4, reason="specific imagery"),
                DimensionScore(dimension="development", score=5, reason="take advances"),
            ]
        ),
        PackageVerdict(
            scores=[
                DimensionScore(dimension="vividness", score=3, reason="some texture"),
                DimensionScore(dimension="development", score=5, reason="take advances"),
            ]
        ),
    ]


def test_render_for_judge_includes_premise_and_shots():
    """Every field a dimension needs to grade must survive into the brief: premise, organizing_principle, each start_keyframe."""
    package = baseline_package()
    premise = "HYDRA"
    render_text = render_for_judge(premise, package)

    assert "HYDRA" in render_text
    assert package.organizing_principle in render_text
    assert all(s.start_keyframe in render_text for s in package.shots)



def test_judge_scorecard():
    verdicts = _fake_verdicts()
    means, low_scores = judge_scorecard(verdicts)
    assert means["vividness"] == 3.0
    assert means["development"] == 5.0
    flagged_dims = [s.dimension for s in low_scores]
    assert "vividness" in flagged_dims
    assert "development" not in flagged_dims


def test_device_distribution():
    package1 = baseline_package()
    package2 = baseline_package()
    package3 = baseline_package()
    package4 = baseline_package()

    package1.device = "embodiment"
    package2.device = "embodiment"
    package3.device = "embodiment"
    package4.device = "wrongness_creep"

    packages = [package1, package2, package3, package4]
    dist = device_distribution(packages)
    assert dist["embodiment"] == 3
    assert dist["wrongness_creep"] == 1