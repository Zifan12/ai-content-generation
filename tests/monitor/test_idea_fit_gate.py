"""Unit tests for IdeaFitGate (Stage A idea-fit gate).

All tests are fully network-free: the LLM is a constructor-injected fake.
Events carry a ``createdAt`` ISO-8601 string in raw_source_data["post"] so
recency can be controlled precisely without mocking datetime.now().
"""

from datetime import datetime, timedelta, timezone

from src.monitor.idea_fit_gate import (
    IdeaFitGate,
    _IdeaFitJudgment,
    _extract_recency_days,
    _UNKNOWN_RECENCY_DAYS,
)
from src.monitor.schemas import ContentMode, TrendingEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(
    *,
    days_old: float | None = 3.0,
    headline: str = "Popular Anime Character Gets Controversial Redesign",
    reaction: str = "I wish they kept the original design, it was perfect",
    origin: str = "scraped",
) -> TrendingEvent:
    """Build a minimal TrendingEvent with a controllable post age.

    Pass ``days_old=None`` to omit the timestamp entirely (simulates a post
    whose raw_source_data carries no parseable date).
    """
    if days_old is not None:
        created_at = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
        raw = {
            "post": {"createdAt": created_at},
            "comment_count": 5,
            "comments_kept": 3,
        }
    else:
        raw = {"post": {}, "comment_count": 0, "comments_kept": 0}

    return TrendingEvent(
        headline=headline,
        subreddit="gaming",
        url="https://reddit.com/r/gaming/test",
        reaction_sample=reaction,
        trendiness_score=5000.0,
        virality_window_hours=24.0,
        raw_source_data=raw,
        origin=origin,
    )


class _FakeLLM:
    """Test double: always returns the same _IdeaFitJudgment; records call count."""

    def __init__(self, judgment: _IdeaFitJudgment) -> None:
        self._judgment = judgment
        self.call_count = 0

    def parse(self, prompt: str, response_model, system: str | None = None):
        assert response_model is _IdeaFitJudgment, (
            f"Gate called LLM with unexpected response_model {response_model!r}"
        )
        self.call_count += 1
        return self._judgment


def _passing_judgment(
    *,
    mode: ContentMode = ContentMode.wish,
    heat_score: float = 0.9,
    reason: str = "Strong wish-fulfillment signal around a recognisable fictional IP.",
) -> _IdeaFitJudgment:
    return _IdeaFitJudgment(
        is_fictional_recognizable=True,
        mode=mode,
        heat_score=heat_score,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# _extract_recency_days
# ---------------------------------------------------------------------------


class TestExtractRecencyDays:
    def test_iso_createdAt(self):
        days = _extract_recency_days(_event(days_old=5.0))
        assert abs(days - 5.0) < 0.05

    def test_unix_created_utc(self):
        ts = (datetime.now(timezone.utc) - timedelta(days=3)).timestamp()
        event = TrendingEvent(
            headline="h",
            subreddit="s",
            url="u",
            reaction_sample="r",
            trendiness_score=1.0,
            virality_window_hours=24.0,
            raw_source_data={"post": {"created_utc": ts}},
            origin="scraped",
        )
        assert abs(_extract_recency_days(event) - 3.0) < 0.05

    def test_missing_timestamp_returns_sentinel(self):
        assert _extract_recency_days(_event(days_old=None)) == _UNKNOWN_RECENCY_DAYS


# ---------------------------------------------------------------------------
# Stale-wave hard sub-gate (no LLM should be called)
# ---------------------------------------------------------------------------


class TestStaleWaveKill:
    def test_stale_event_killed_without_llm_call(self):
        llm = _FakeLLM(_passing_judgment())
        gate = IdeaFitGate(llm=llm, stale_days_threshold=14.0)

        result = gate.evaluate(_event(days_old=21.0))

        assert not result.idea_fit
        assert result.kill_reason is not None and "stale_wave" in result.kill_reason
        assert result.recency_days > 14.0
        assert result.heat_score == 0.0
        assert llm.call_count == 0, "LLM must NOT be called for stale events"

    def test_stellar_blade_evie_bug_002_regression(self):
        """BUG-002 regression: June-6 reveal rendered June-27 (~21 days old) must be killed."""
        llm = _FakeLLM(_passing_judgment())
        gate = IdeaFitGate(llm=llm, stale_days_threshold=14.0)
        event = _event(
            days_old=21.0,
            headline="Stellar Blade got an Adult Redesign and fans are NOT happy",
        )
        result = gate.evaluate(event)

        assert not result.idea_fit
        assert llm.call_count == 0

    def test_missing_timestamp_killed_as_stale(self):
        """Events with no parseable timestamp are treated as stale — no silent pass."""
        llm = _FakeLLM(_passing_judgment())
        gate = IdeaFitGate(llm=llm, stale_days_threshold=14.0)

        result = gate.evaluate(_event(days_old=None))

        assert not result.idea_fit
        assert llm.call_count == 0

    def test_borderline_hot_event_reaches_llm(self):
        """Just under the threshold → should proceed to LLM."""
        llm = _FakeLLM(_passing_judgment())
        gate = IdeaFitGate(llm=llm, stale_days_threshold=14.0)

        gate.evaluate(_event(days_old=13.9))

        assert llm.call_count == 1

    def test_custom_threshold_respected(self):
        llm = _FakeLLM(_passing_judgment())
        gate = IdeaFitGate(llm=llm, stale_days_threshold=3.0)

        result = gate.evaluate(_event(days_old=4.0))

        assert not result.idea_fit
        assert llm.call_count == 0


# ---------------------------------------------------------------------------
# LLM-based checks (recency passes; LLM decides)
# ---------------------------------------------------------------------------


class TestLLMChecks:
    def test_non_fictional_killed(self):
        llm = _FakeLLM(
            _IdeaFitJudgment(
                is_fictional_recognizable=False,
                mode=ContentMode.other,
                heat_score=0.6,
                reason="This is about a real athlete, not a fictional character.",
            )
        )
        gate = IdeaFitGate(llm=llm)

        result = gate.evaluate(_event(days_old=2.0))

        assert not result.idea_fit
        assert result.kill_reason is not None and "not_fictional" in result.kill_reason
        assert result.heat_score == 0.6

    def test_meme_phrased_wave_now_passes(self):
        """A recognisable-fictional wave the LLM reads as meme-ish (satire) is
        no longer killed: the gate stopped predicting rendered-payoff — that is
        the craft gate's call on the actual pitch. Only the fictional + recency
        floors remain."""
        llm = _FakeLLM(
            _IdeaFitJudgment(
                is_fictional_recognizable=True,
                mode=ContentMode.satire,
                heat_score=0.4,
                reason="Jokey reactions, but a recognisable fictional cast.",
            )
        )
        gate = IdeaFitGate(llm=llm)

        result = gate.evaluate(_event(days_old=2.0))

        assert result.idea_fit
        assert result.kill_reason is None
        assert result.mode == ContentMode.satire

    def test_wish_event_passes(self):
        llm = _FakeLLM(_passing_judgment(mode=ContentMode.wish, heat_score=0.95))
        gate = IdeaFitGate(llm=llm)

        result = gate.evaluate(_event(days_old=2.0))

        assert result.idea_fit
        assert result.mode == ContentMode.wish
        assert result.kill_reason is None
        assert result.heat_score == 0.95

    def test_satire_event_passes(self):
        llm = _FakeLLM(_passing_judgment(mode=ContentMode.satire, heat_score=0.75))
        gate = IdeaFitGate(llm=llm)

        result = gate.evaluate(_event(days_old=5.0))

        assert result.idea_fit
        assert result.mode == ContentMode.satire
        assert result.kill_reason is None

    def test_recency_days_propagated_to_result(self):
        llm = _FakeLLM(_passing_judgment())
        gate = IdeaFitGate(llm=llm)

        result = gate.evaluate(_event(days_old=7.0))

        assert abs(result.recency_days - 7.0) < 0.1

    def test_empty_reaction_sample_killed_without_llm(self):
        """Empty reaction_sample must be killed before calling the LLM."""
        llm = _FakeLLM(_passing_judgment())
        gate = IdeaFitGate(llm=llm)
        event = _event(days_old=2.0, reaction="   ")

        result = gate.evaluate(event)

        assert not result.idea_fit
        assert result.kill_reason is not None and "no_reactions" in result.kill_reason
        assert llm.call_count == 0


# ---------------------------------------------------------------------------
# Task 6 — origin-aware branching (manual vs scraped)
# ---------------------------------------------------------------------------


class TestManualOrigin:
    """Manual (--topic) events: skip recency kill, warn-not-kill on real-person."""

    def test_manual_missing_timestamp_not_killed_for_staleness(self):
        """No createdAt -> recency_days==999, but manual origin must NOT be
        auto-killed at Check 1; the LLM is reached instead."""
        llm = _FakeLLM(_passing_judgment())
        gate = IdeaFitGate(llm=llm, stale_days_threshold=14.0)

        result = gate.evaluate(_event(days_old=None, origin="manual"))

        assert result.idea_fit
        assert abs(result.recency_days - 999.0) < 1.0, "recency still propagated"
        assert llm.call_count == 1, "LLM must be reached for manual stale-is-irrelevant path"

    def test_manual_real_person_passes_with_warning(self):
        """LLM says not fictional (real person).  Manual origin must PASS with
        idea_fit=True, kill_reason=None, and a real-person warning in reason."""
        llm = _FakeLLM(
            _IdeaFitJudgment(
                is_fictional_recognizable=False,
                mode=ContentMode.other,
                heat_score=0.6,
                reason="This is about a real athlete, not a fictional character.",
            )
        )
        gate = IdeaFitGate(llm=llm)

        result = gate.evaluate(_event(days_old=2.0, origin="manual"))

        assert result.idea_fit, "manual real-person event must not be hard-killed"
        assert result.kill_reason is None, "warning lives in reason, not kill_reason"
        assert "real-person" in result.reason.lower() or "real person" in result.reason.lower(), (
            f"reason should carry real-person warning, got: {result.reason!r}"
        )

    def test_scraped_still_killed_for_staleness(self):
        """Regression: scraped events with no timestamp still die at Check 1."""
        llm = _FakeLLM(_passing_judgment())
        gate = IdeaFitGate(llm=llm, stale_days_threshold=14.0)

        result = gate.evaluate(_event(days_old=None, origin="scraped"))

        assert not result.idea_fit
        assert llm.call_count == 0, "scraped stale path must short-circuit before LLM"

    def test_scraped_real_person_still_killed(self):
        """Regression: scraped events judged not-fictional still die at Check 2."""
        llm = _FakeLLM(
            _IdeaFitJudgment(
                is_fictional_recognizable=False,
                mode=ContentMode.other,
                heat_score=0.6,
                reason="This is about a real athlete.",
            )
        )
        gate = IdeaFitGate(llm=llm)

        result = gate.evaluate(_event(days_old=2.0, origin="scraped"))

        assert not result.idea_fit
        assert result.kill_reason is not None and "not_fictional" in result.kill_reason
