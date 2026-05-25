"""
Virality classification rubric — single source of truth for thresholds.

PIPELINE ROLE:
  Shared rubric module used by:
    - scripts/label.py (human-in-the-loop ground-truth labeling)
    - src/analysis/scorer.py (RuleBasedScorer baseline for eval gates)

WHY THIS FILE EXISTS:
  Previously the labeling heuristic was duplicated between scripts/label.py
  and src/analysis/scorer.py with a `CRITICAL SYNC` comment warning humans
  to keep them in sync. Comments don't enforce invariants — refactors do.
  This module centralizes the thresholds + formula so changing the rubric
  is a one-file edit and both consumers automatically agree.

WHAT IT DOES:
  weighted_er(views, likes, comments, shares) -> float
    Weighted engagement rate as percentage. Comments weighted 2x, shares 3x
    because deliberate engagement is a stronger signal than passive likes.

  classify(views, weighted_er) -> tuple[str, str]
    Decision tree mapping (views, weighted_er) to one of:
    "viral" | "mid" | "flop" | "suspicious"
    Returns the class + a human-readable reasoning string for audit trails.

DECISION TREE (checked in order):
  1. views >= 500K AND wER <  1.0%             -> "suspicious"  (likely bot/gamed)
  2. views >= 500K AND wER >= 4.0%             -> "viral"       (high reach + strong engagement)
  3. views >= 500K AND 1.5% <= wER < 4.0%      -> "mid"         (high reach, moderate engagement)
  4. 50K <= views < 500K AND wER >= 1.5%       -> "mid"         (growing, good engagement)
  5. else                                       -> "flop"        (low reach or weak engagement)

USAGE:
  from src.analysis.rubric import weighted_er, classify

  er = weighted_er(views=100_000, likes=5_000, comments=200, shares=50)
  virality_class, reason = classify(views=100_000, weighted_er=er)
"""

# View thresholds in absolute counts.
HIGH_VIEW_THRESHOLD = 500_000
MID_VIEW_THRESHOLD = 50_000

# Weighted engagement rate thresholds in percent.
SUSPICIOUS_ER_THRESHOLD = 1.0
MID_ER_THRESHOLD = 1.5
VIRAL_ER_THRESHOLD = 4.0


def weighted_er(views: int, likes: int, comments: int, shares: int) -> float:
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
        Weighted engagement rate as percentage (0.0 if views == 0).
    """
    if views == 0:
        return 0.0
    return (likes * 1 + comments * 2 + shares * 3) / views * 100


def classify(views: int, weighted_er: float) -> tuple[str, str]:
    """
    Apply the rubric decision tree to classify virality.

    Args:
        views: Total video views.
        weighted_er: Weighted engagement rate as percentage.

    Returns:
        Tuple of (virality_class, reason_string). Class is one of:
        "viral", "mid", "flop", "suspicious".

    The 500K view threshold catches viral-in-reach videos; the 50K threshold
    catches growing videos with strong engagement. The suspicious threshold
    prevents high-reach low-engagement spam/bot videos from being labeled viral.
    """
    if views >= HIGH_VIEW_THRESHOLD and weighted_er < SUSPICIOUS_ER_THRESHOLD:
        return "suspicious", f"views>={HIGH_VIEW_THRESHOLD:,} but wER={weighted_er:.2f}%<{SUSPICIOUS_ER_THRESHOLD}%"
    if views >= HIGH_VIEW_THRESHOLD and weighted_er >= VIRAL_ER_THRESHOLD:
        return "viral", f"views>={HIGH_VIEW_THRESHOLD:,}, wER={weighted_er:.2f}%>={VIRAL_ER_THRESHOLD}%"
    if views >= HIGH_VIEW_THRESHOLD and weighted_er >= MID_ER_THRESHOLD:
        return "mid", f"views>={HIGH_VIEW_THRESHOLD:,}, {MID_ER_THRESHOLD}%<=wER={weighted_er:.2f}%<{VIRAL_ER_THRESHOLD}%"
    if views >= MID_VIEW_THRESHOLD and weighted_er >= MID_ER_THRESHOLD:
        return "mid", f"{MID_VIEW_THRESHOLD:,}<=views<{HIGH_VIEW_THRESHOLD:,}, wER={weighted_er:.2f}%>={MID_ER_THRESHOLD}%"
    return "flop", f"views={views:,}<{MID_VIEW_THRESHOLD:,} or wER={weighted_er:.2f}%<{MID_ER_THRESHOLD}%"
