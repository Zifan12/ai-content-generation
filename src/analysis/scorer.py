"""
Rule-based virality classifier — deterministic baseline for eval gates.

PIPELINE ROLE:
  Used by P1 eval harness (test_blueprint_eval.py) as baseline scorer.
  Provides deterministic, cost-free virality classification (no LLM calls).

WHY THIS FILE EXISTS:
  Evals need a "ground truth" baseline to measure against. This module implements
  the labeling rubric (same heuristics as scripts/label.py) so that:
  - eval harness can score inputs deterministically
  - all downstream code (generation, RAG, etc.) can classify without LLM cost
  - changes to scoring rules are centralized and testable

WHAT IT DOES:
  RuleBasedScorer.score(views, likes, comments, shares) → ScorerResult
  
  Returns:
    - virality_class: one of "viral", "mid", "flop", "suspicious"
    - score: numeric 0.0/0.5/1.0 for ranking
    - weighted_er: the underlying engagement metric
    - reasoning: human-readable explanation (for audit/debugging)

SCORING RULES (exact match to labeling rubric):
  1. views ≥ 500K AND wER < 1%  → "suspicious" (fraud risk: high reach, low engagement)
  2. views ≥ 500K AND wER ≥ 4%  → "viral" (organic: reach + strong engagement)
  3. views ≥ 500K AND 1.5% ≤ wER < 4%  → "mid" (reach present, engagement moderate)
  4. 50K ≤ views < 500K AND wER ≥ 1.5%  → "mid" (growing videos with good engagement)
  5. else → "flop" (low reach or weak engagement)

WEIGHTED ENGAGEMENT RATE:
  wER = (likes*1 + comments*2 + shares*3) / views * 100
  
  Comments/shares weighted 2x/3x because they're harder-earned than likes.
  A video with 1% likes but 4% comments/shares will score higher (stronger signal).

CRITICAL SYNC:
  This module's heuristics MUST match scripts/label.py exactly. If you change
  thresholds in label.py, update this file too. Both are part of P1 foundation.

USAGE:
  from src.analysis.scorer import RuleBasedScorer
  scorer = RuleBasedScorer()
  result = scorer.score(views=100_000, likes=5000, comments=200, shares=50)
  print(result.virality_class)  # "mid"
  print(result.reasoning)  # "50K≤views<500K, wER=8.50%≥1.5%"
"""

from dataclasses import dataclass

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
    score: float # 0.0 (flop/suspicious), 0.5 (mid), 1.0 (viral)
    weighted_er: float
    reasoning: str

class RuleBasedScorer:
    """
    Weighted ER + view threshold classifier. Matches labeling rubric exactly.
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
        weighted_er = self._weighted_er(views, likes, comments, shares)
        virality_class, reasoning = self._classify(views, weighted_er)
        score = {"viral": 1.0, "mid": 0.5, "flop": 0.0, "suspicious": 0.0}[virality_class]
        return ScorerResult(
            virality_class,
            score,
            weighted_er,
            reasoning,
        )

    def _weighted_er(self, views: int, likes: int, comments: int, shares: int) -> float:
        """
        Compute weighted engagement rate (wER) as a percentage.
        
        Formula: (likes*1 + comments*2 + shares*3) / views * 100
        
        Rationale: Not all engagement is equal. Likes are passive; comments and
        shares require deliberate user action. Weighting by 2x and 3x respectively
        ensures videos with deep engagement score higher than those with only
        passive likes, even if total engagement counts are similar.
        
        Args:
            views: Total video views.
            likes: Total likes.
            comments: Total comments.
            shares: Total shares.
        
        Returns:
            Weighted engagement rate as percentage (0.0 if views==0).
        """
        if views == 0:
            return 0.0
        return (likes * 1 + comments * 2 + shares * 3) / views * 100
        
    def _classify(self, views: int, weighted_er: float) -> tuple[str, str]:
        """
        Apply decision tree to classify virality based on views and wER.
        
        Rules (checked in order):
        1. views ≥ 500K AND wER < 1%  → "suspicious" (likely bot-boosted/gamed)
        2. views ≥ 500K AND wER ≥ 4%  → "viral" (high reach + strong engagement)
        3. views ≥ 500K AND 1.5% ≤ wER < 4%  → "mid" (reach present, engagement moderate)
        4. 50K ≤ views < 500K AND wER ≥ 1.5%  → "mid" (organic growth, good engagement)
        5. else  → "flop" (low reach or weak engagement)
        
        The 500K view threshold catches viral-in-reach videos; the 50K threshold
        catches growing videos with strong engagement. The suspicious threshold
        prevents high-reach, low-engagement spam/bot videos from being labeled viral.
        
        Args:
            views: Total video views.
            weighted_er: Weighted engagement rate (%).
        
        Returns:
            Tuple of (virality_class, reason_string).
        """
        if views >= 500_000 and weighted_er < 1.0:
            return "suspicious", f"views≥500K but wER={weighted_er:.2f}%<1%"
        if views >= 500_000 and weighted_er >= 4.0:
            return "viral", f"views≥500K, wER={weighted_er:.2f}%≥4%"
        if views >= 500_000 and weighted_er >= 1.5:
            return "mid", f"views≥500K, 1.5%≤wER={weighted_er:.2f}%<4%"
        if views >= 50_000 and weighted_er >= 1.5:
            return "mid", f"50K≤views<500K, wER={weighted_er:.2f}%≥1.5%"
        return "flop", f"views={views:,}<50K or wER={weighted_er:.2f}%<1.5%"