"""
Rule-based virality classifier — deterministic baseline for eval gates.

PIPELINE ROLE:
  Registered by the eval harness (src/evals/harness.py) as the
  ``rule-based-scorer`` component.
  Provides deterministic, cost-free virality classification (no LLM calls).

WHY THIS FILE EXISTS:
  Evals need a "ground truth" baseline to measure against. This module wraps
  the shared rubric (src/analysis/rubric.py) in a ScorerResult dataclass so
  the eval harness has a uniform scorer interface across components.

WHAT IT DOES:
  RuleBasedScorer.score(views, likes, comments, shares) -> ScorerResult

  Returns:
    - virality_class: one of "viral", "mid", "flop", "suspicious"
    - score: numeric 0.0/0.5/1.0 for ranking
    - weighted_er: the underlying engagement metric
    - reasoning: human-readable explanation (for audit/debugging)

  All threshold/formula logic lives in src.analysis.rubric. This module
  exists only to adapt that rubric into the scorer-callable shape expected
  by EvalHarness.

USAGE:
  from src.analysis.scorer import RuleBasedScorer
  scorer = RuleBasedScorer()
  result = scorer.score(views=100_000, likes=5000, comments=200, shares=50)
  print(result.virality_class)
  print(result.reasoning)
"""

from dataclasses import dataclass

from src.analysis.rubric import classify, weighted_er


_SCORE_MAP = {
    "viral": 1.0,
    "mid": 0.5,
    "flop": 0.0,
    "suspicious": 0.0,
}


@dataclass
class ScorerResult:
    """
    Output of virality classification.

    Attributes:
        virality_class: One of "viral", "mid", "flop", "suspicious".
        score: Numeric score for ranking: 1.0 (viral), 0.5 (mid), 0.0 (flop/suspicious).
        weighted_er: Weighted engagement rate (%) used by classifier.
        reasoning: Human-readable explanation of the classification.
    """
    virality_class: str
    score: float
    weighted_er: float
    reasoning: str


class RuleBasedScorer:
    """
    Weighted ER + view threshold classifier. Delegates to src.analysis.rubric
    for the actual decision tree so the rubric is shared with scripts/label.py.
    """

    def score(self, views: int, likes: int, comments: int, shares: int) -> ScorerResult:
        """
        Classify a video's virality based on views and engagement metrics.

        Args:
            views: Total video views.
            likes: Total likes.
            comments: Total comments.
            shares: Total shares.

        Returns:
            ScorerResult with virality_class, numeric score, weighted_er, and reasoning.
        """
        er = weighted_er(views, likes, comments, shares)
        virality_class, reasoning = classify(views, er)
        return ScorerResult(
            virality_class=virality_class,
            score=_SCORE_MAP[virality_class],
            weighted_er=er,
            reasoning=reasoning,
        )
