import pytest
from src.analysis.scorer import RuleBasedScorer


@pytest.fixture
def scorer():
    return RuleBasedScorer()


def test_viral(scorer):
    result = scorer.score(views=600_000, likes=30_000, comments=5_000, shares=3_000)
    assert result.virality_class == "viral"
    assert result.score == 1.0


def test_mid_high_views_mid_er(scorer):
    result = scorer.score(views=600_000, likes=10_000, comments=1_000, shares=500)
    assert result.virality_class == "mid"
    assert result.score == 0.5


def test_mid_low_views(scorer):
    result = scorer.score(views=80_000, likes=2_000, comments=500, shares=200)
    assert result.virality_class == "mid"
    assert result.score == 0.5


def test_flop(scorer):
    result = scorer.score(views=10_000, likes=100, comments=10, shares=5)
    assert result.virality_class == "flop"
    assert result.score == 0.0


def test_suspicious(scorer):
    result = scorer.score(views=700_000, likes=100, comments=50, shares=10)
    assert result.virality_class == "suspicious"
    assert result.score == 0.0


def test_zero_views(scorer):
    result = scorer.score(views=0, likes=0, comments=0, shares=0)
    assert result.virality_class == "flop"
    assert result.score == 0.0