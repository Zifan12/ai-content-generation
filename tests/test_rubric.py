"""
Tests for src/analysis/rubric.py — single source of truth for virality rules.

Coverage strategy:
  - Pin every branch of classify() so refactors can't silently shift thresholds.
  - Test weighted_er formula + zero-division edge case.
  - Test boundary conditions at every threshold (>=, <).
"""

import pytest

from src.analysis.rubric import (
    HIGH_VIEW_THRESHOLD,
    MID_VIEW_THRESHOLD,
    SUSPICIOUS_ER_THRESHOLD,
    MID_ER_THRESHOLD,
    VIRAL_ER_THRESHOLD,
    classify,
    weighted_er,
)


# ---------- weighted_er ----------

def test_weighted_er_formula():
    """(1*1 + 2*2 + 3*3) / 100 * 100 == 14.0 (float-tolerant)."""
    assert weighted_er(views=100, likes=1, comments=2, shares=3) == pytest.approx(14.0)


def test_weighted_er_zero_views_returns_zero():
    assert weighted_er(views=0, likes=999, comments=999, shares=999) == 0.0


def test_weighted_er_zero_engagement_returns_zero():
    assert weighted_er(views=1000, likes=0, comments=0, shares=0) == 0.0


def test_weighted_er_comments_weighted_2x():
    """1 comment > 1 like at same view count."""
    er_likes = weighted_er(views=100, likes=10, comments=0, shares=0)
    er_comments = weighted_er(views=100, likes=0, comments=10, shares=0)
    assert er_comments == 2 * er_likes


def test_weighted_er_shares_weighted_3x():
    er_likes = weighted_er(views=100, likes=10, comments=0, shares=0)
    er_shares = weighted_er(views=100, likes=0, comments=0, shares=10)
    assert er_shares == 3 * er_likes


# ---------- classify: each branch ----------

def test_classify_suspicious_high_views_low_er():
    cls, reason = classify(views=600_000, weighted_er=0.5)
    assert cls == "suspicious"
    assert "wER=0.50" in reason


def test_classify_viral_high_views_high_er():
    cls, _ = classify(views=600_000, weighted_er=5.0)
    assert cls == "viral"


def test_classify_mid_high_views_mid_er():
    cls, _ = classify(views=600_000, weighted_er=2.5)
    assert cls == "mid"


def test_classify_mid_low_views_good_er():
    cls, _ = classify(views=80_000, weighted_er=2.0)
    assert cls == "mid"


def test_classify_flop_low_views():
    cls, _ = classify(views=10_000, weighted_er=10.0)
    assert cls == "flop"


def test_classify_flop_low_er():
    cls, _ = classify(views=600_000, weighted_er=1.2)
    # 1.2 is between SUSPICIOUS (1.0) and MID (1.5) thresholds at high views.
    # Not suspicious (>= 1.0), not viral (< 4.0), not mid (< 1.5) -> flop.
    assert cls == "flop"


# ---------- classify: boundary conditions ----------

def test_classify_boundary_suspicious_er_exact():
    """wER == 1.0 is NOT suspicious (uses strict <)."""
    cls, _ = classify(views=HIGH_VIEW_THRESHOLD, weighted_er=SUSPICIOUS_ER_THRESHOLD)
    assert cls != "suspicious"


def test_classify_boundary_viral_er_exact():
    """wER == 4.0 is viral (uses >=)."""
    cls, _ = classify(views=HIGH_VIEW_THRESHOLD, weighted_er=VIRAL_ER_THRESHOLD)
    assert cls == "viral"


def test_classify_boundary_mid_er_exact():
    """wER == 1.5 at high views is mid."""
    cls, _ = classify(views=HIGH_VIEW_THRESHOLD, weighted_er=MID_ER_THRESHOLD)
    assert cls == "mid"


def test_classify_boundary_mid_view_threshold():
    """views == 50_000 with mid wER is mid."""
    cls, _ = classify(views=MID_VIEW_THRESHOLD, weighted_er=MID_ER_THRESHOLD)
    assert cls == "mid"


def test_classify_below_mid_views():
    """views == 49_999 is flop regardless of wER."""
    cls, _ = classify(views=MID_VIEW_THRESHOLD - 1, weighted_er=10.0)
    assert cls == "flop"


# ---------- classify: reason string contains numbers for audit ----------

def test_classify_reason_includes_views_and_er():
    _, reason = classify(views=600_000, weighted_er=2.5)
    assert "wER=2.50" in reason
