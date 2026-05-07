"""
Rule-based virality classifier matching the labeling rubric.

Single source of truth for converting raw video stats (views, likes, comments,
shares) into a virality_class label. Used by both the eval harness as the
baseline scorer and any downstream code that needs a deterministic class
without an LLM call.
"""

from dataclasses import dataclass

@dataclass
class ScorerResult:
    virality_class: str
    score: float # 0.0 (flop/suspicious), 0.5 (mid), 1.0 (viral)
    weighted_er: float
    reasoning: str

class RuleBasedScorer:
    """
    Weighted ER + view threshold classifier. Matches labeling rubric exactly.
    """

    def score(self, views: int, likes: int, comments: int, shares: int) -> ScorerResult:
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
        if views == 0:
            return 0.0
        return (likes * 1 + comments * 2 + shares * 3) / views * 100
        
    def _classify(self, views: int, weighted_er: float) -> tuple[str, str]:
        if views >= 500_000 and weighted_er < 1.0:
            return "suspicious", f"views≥500K but wER={weighted_er:.2f}%<1%"
        if views >= 500_000 and weighted_er >= 4.0:
            return "viral", f"views≥500K, wER={weighted_er:.2f}%≥4%"
        if views >= 500_000 and weighted_er >= 1.5:
            return "mid", f"views≥500K, 1.5%≤wER={weighted_er:.2f}%<4%"
        if views >= 50_000 and weighted_er >= 1.5:
            return "mid", f"50K≤views<500K, wER={weighted_er:.2f}%≥1.5%"
        return "flop", f"views={views:,}<50K or wER={weighted_er:.2f}%<1.5%"