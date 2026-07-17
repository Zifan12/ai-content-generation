"""Tests for the Topic Brief checker + bounded repair loop (Exilus ticket 03).

Per the PRD's Testing Decisions, these assert external behavior only --
artifact shape/content and control flow (halt, repair, stamp) -- never
internal call order or prompt wording. All LLMs and the context-agent
re-entry point are fakes; the DB session is the same sqlite-in-memory
fixture ticket 01's tests use (no pgvector column on this table, so a real
Postgres connection buys nothing here).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.monitor.brief_checker import (
    BriefCheckVerdict,
    SpecificityVerdict,
    check_and_repair_brief,
    check_brief,
    check_code_layer,
    check_specificity_layer,
)
from src.monitor.context_agent import ContextAgentState, compose_topic_brief
from src.monitor.schemas import BriefField, BriefFieldDraft, TopicBrief, TopicBriefDraft
from src.monitor.topic_brief import load_topic_brief


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


GATHERED_URLS = ["https://reddit.com/r/x/comments/1", "https://example.com/article"]


def _passing_brief() -> TopicBrief:
    """A brief whose four checked fields all pass the code layer."""
    return TopicBrief(
        identity=BriefField(content="Wistoria is a fantasy anime.", citations=[GATHERED_URLS[0]]),
        recent_events=BriefField(content="Season 2 finale aired June 28.", citations=[GATHERED_URLS[1]]),
        key_characters=BriefField(content="Elfaria and Will are the pair.", citations=[GATHERED_URLS[0]]),
        why_people_care=BriefField(content="Fans wanted the reunion.", citations=[GATHERED_URLS[1]]),
        open_unknowns=[],
    )


def _all_specific_verdict() -> SpecificityVerdict:
    return SpecificityVerdict(
        reasoning="every field names concrete details unique to this topic",
        identity_specific=True,
        recent_events_specific=True,
        key_characters_specific=True,
        why_people_care_specific=True,
    )


class FakeSpecificityLLM:
    """Returns queued SpecificityVerdicts in order, one per check_specificity_layer call."""

    def __init__(self, verdicts: list[SpecificityVerdict]) -> None:
        self._verdicts = list(verdicts)
        self.call_count = 0

    def parse(self, prompt, response_model, **kwargs):
        self.call_count += 1
        return self._verdicts.pop(0)


class FakeContextAgent:
    """Stub for `check_and_repair_brief`'s `context_agent` param: only needs
    `reenter_with_query`. Returns queued (urls, draft) pairs as the "repaired"
    state, in order -- one per repair round. Bumps `tavily_calls` by 1 each
    call (a real repair round's forced action -- see module docstring's
    "IMPLEMENTATION CHOICES" -- always targets tavily_search), so it models
    "real progress happened" for FIX 6's no-new-tool-calls refusal check;
    RefusedFakeContextAgent below overrides this to model the opposite.
    """

    def __init__(self, repaired: list[tuple[list[str], TopicBriefDraft]]) -> None:
        self._repaired = list(repaired)
        self.calls: list[tuple[str, str]] = []

    def reenter_with_query(self, state, action, query):
        self.calls.append((action, query))
        urls, draft = self._repaired.pop(0)
        return state.model_copy(
            update={
                "urls": urls,
                "brief_draft": draft,
                "tavily_calls": state.tavily_calls + 1,
            }
        )


class RefusedFakeContextAgent(FakeContextAgent):
    """Simulates a context_agent whose reenter_with_query is refused by
    decide_next_step's ceiling (the run's cumulative budget was already
    exhausted before this round) -- mirrors what a real refused reenter's
    ``_drive_loop`` actually does: no act node runs (call counts unchanged),
    but ``finalize`` still re-synthesizes ``brief_draft`` once regardless
    (see ``test_reenter_with_query_refuses_when_budget_already_exhausted``
    in ``test_context_agent.py``, which exercises this on the real
    ``ContextAgent``)."""

    def reenter_with_query(self, state, action, query):
        self.calls.append((action, query))
        _, draft = self._repaired.pop(0)
        return state.model_copy(update={"brief_draft": draft})  # urls/calls unchanged


def _state(urls: list[str]) -> ContextAgentState:
    return ContextAgentState(
        topic="Wistoria",
        reddit_text="",
        web_text="",
        reddit_calls=1,
        tavily_calls=1,
        apify_cost_estimate=0.1,
        within_community="",
        next_action="stop",
        next_query="",
        urls=urls,
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )


def _draft(**overrides) -> TopicBriefDraft:
    base = dict(
        identity=BriefFieldDraft(content="Wistoria is a fantasy anime.", citations=[GATHERED_URLS[0]]),
        recent_events=BriefFieldDraft(content="Season 2 finale aired June 28.", citations=[GATHERED_URLS[1]]),
        key_characters=BriefFieldDraft(content="Elfaria and Will are the pair.", citations=[GATHERED_URLS[0]]),
        why_people_care=BriefFieldDraft(content="Fans wanted the reunion.", citations=[GATHERED_URLS[1]]),
        open_unknowns=[],
    )
    base.update(overrides)
    return TopicBriefDraft(**base)


# ---------------------------------------------------------------------------
# Layer 1: code checks (AC1-3)
# ---------------------------------------------------------------------------


def test_code_layer_all_pass_no_llm_needed():
    """AC1: every field non-empty + every citation in the gathered set ->
    every field passes, and check_code_layer itself never touches an LLM
    (it takes no llm parameter at all)."""
    result = check_code_layer(_passing_brief(), GATHERED_URLS)

    assert result == {
        "identity": True,
        "recent_events": True,
        "key_characters": True,
        "why_people_care": True,
    }


def test_code_layer_flags_empty_field():
    """AC2: an empty field fails the code layer regardless of citations."""
    brief = _passing_brief()
    brief.recent_events = BriefField(content="   ", citations=[GATHERED_URLS[1]])

    result = check_code_layer(brief, GATHERED_URLS)

    assert result["recent_events"] is False
    assert result["identity"] is True


def test_code_layer_flags_citation_less_field():
    """Test-notes case: a field with real content but zero citations fails
    the code layer -- a citation-less field is exactly what layer 1 must
    catch (context_agent's BRIEF_SYSTEM_PROMPT explicitly allows the
    researcher to leave a field uncited; the checker is what grades it)."""
    brief = _passing_brief()
    brief.identity = BriefField(content="Wistoria is a fantasy anime.", citations=[])

    result = check_code_layer(brief, GATHERED_URLS)

    assert result["identity"] is False


def test_code_layer_flags_citation_outside_gathered_set():
    """AC3: a citation URL not in the gathered set fails the field, even
    though the field has real content and A citation string present."""
    brief = _passing_brief()
    brief.why_people_care = BriefField(
        content="Fans wanted the reunion.", citations=["https://not-really-gathered.example/x"]
    )

    result = check_code_layer(brief, GATHERED_URLS)

    assert result["why_people_care"] is False
    assert result["identity"] is True  # untouched fields still pass


# ---------------------------------------------------------------------------
# Layer 2: specificity judge + combined verdict (AC4)
# ---------------------------------------------------------------------------


def test_specificity_layer_returns_llm_verdict():
    fake = FakeSpecificityLLM([_all_specific_verdict()])

    verdict = check_specificity_layer(_passing_brief(), "Wistoria", fake)

    assert verdict.identity_specific is True
    assert fake.call_count == 1


def test_check_brief_layer2_can_fail_a_field_layer1_passed():
    """AC4: a brief passing every code check can still fail overall because
    the specificity judge independently fails one field."""
    fake = FakeSpecificityLLM(
        [
            SpecificityVerdict(
                reasoning="why_people_care is generic filler",
                identity_specific=True,
                recent_events_specific=True,
                key_characters_specific=True,
                why_people_care_specific=False,
            )
        ]
    )

    verdict = check_brief(_passing_brief(), "Wistoria", GATHERED_URLS, fake)

    assert isinstance(verdict, BriefCheckVerdict)
    assert verdict.code_passes == {
        "identity": True,
        "recent_events": True,
        "key_characters": True,
        "why_people_care": True,
    }
    assert verdict.passes is False
    assert verdict.failing_fields == ["why_people_care"]


def test_check_brief_passes_when_both_layers_pass():
    fake = FakeSpecificityLLM([_all_specific_verdict()])

    verdict = check_brief(_passing_brief(), "Wistoria", GATHERED_URLS, fake)

    assert verdict.passes is True
    assert verdict.failing_fields == []


# ---------------------------------------------------------------------------
# Repair-round orchestration (AC5-10)
# ---------------------------------------------------------------------------


def test_passing_brief_flows_onward_no_halt_no_repair(db):
    """AC5: a brief passing both layers on the first check returns
    halted=False, uses zero repair rounds, and never touches the fake
    context_agent (no repair call) or persists anything."""
    brief = compose_topic_brief(_draft())
    state = _state(GATHERED_URLS)
    fake_llm = FakeSpecificityLLM([_all_specific_verdict()])
    fake_agent = FakeContextAgent([])

    outcome = check_and_repair_brief("Wistoria", brief, state, fake_agent, fake_llm, db)

    assert outcome.halted is False
    assert outcome.rounds_used == 0
    assert fake_agent.calls == []
    assert outcome.brief.identity.verified is True
    assert outcome.brief.why_people_care.verified is True
    # nothing persisted on the passing path -- that's the driver's job
    assert load_topic_brief("Wistoria", db) is None


def test_field_fixed_in_round_one_carries_no_unverified_stamp(db):
    """AC8: a field failing round 1's check but fixed by round 1's repair
    passes on the next check and carries no UNVERIFIED stamp."""
    bad_draft = _draft(
        why_people_care=BriefFieldDraft(content="Fans wanted the reunion.", citations=[])
    )
    fixed_draft = _draft()  # why_people_care now carries a grounded citation
    brief = compose_topic_brief(bad_draft)
    state = _state(GATHERED_URLS)

    fake_llm = FakeSpecificityLLM([_all_specific_verdict(), _all_specific_verdict()])
    fake_agent = FakeContextAgent([(GATHERED_URLS, fixed_draft)])

    outcome = check_and_repair_brief("Wistoria", brief, state, fake_agent, fake_llm, db)

    assert outcome.halted is False
    assert outcome.rounds_used == 1
    assert len(fake_agent.calls) == 1
    assert fake_agent.calls[0][0] == "tavily_search"
    assert "why people care" in fake_agent.calls[0][1]
    assert outcome.brief.why_people_care.verified is True
    assert load_topic_brief("Wistoria", db) is None  # still not persisted here


def test_repair_loop_respects_two_round_bound_then_halts(db):
    """AC6/AC7/AC9: a field that never resolves triggers exactly 2 repair
    rounds (no 3rd attempted), then the brief is persisted with UNVERIFIED
    on exactly that field and the outcome is a distinct halt signal."""
    bad_draft = _draft(
        why_people_care=BriefFieldDraft(content="Fans wanted the reunion.", citations=[])
    )
    brief = compose_topic_brief(bad_draft)
    state = _state(GATHERED_URLS)

    # Every check (initial + after each repair) sees the same unresolved gap.
    fake_llm = FakeSpecificityLLM([_all_specific_verdict()] * 3)
    fake_agent = FakeContextAgent(
        [(GATHERED_URLS, bad_draft), (GATHERED_URLS, bad_draft)]
    )

    outcome = check_and_repair_brief("Wistoria", brief, state, fake_agent, fake_llm, db)

    assert len(fake_agent.calls) == 2  # exactly 2 repair rounds, no 3rd
    assert outcome.halted is True
    assert outcome.rounds_used == 2
    assert outcome.brief.why_people_care.verified is False
    assert outcome.brief.identity.verified is True
    assert outcome.brief.recent_events.verified is True
    assert outcome.brief.key_characters.verified is True

    persisted = load_topic_brief("Wistoria", db)
    assert persisted is not None
    assert persisted.why_people_care.verified is False
    assert persisted.identity.verified is True


def test_refused_reentry_skips_recheck_and_halts_immediately(db):
    """FIX 6: when re-entry performs zero new tool calls (the run's
    cumulative budget was already exhausted before this round -- distinct
    from this function's OWN max_repair_rounds bound, which has nothing to
    do with this case), check_and_repair_brief must not spend a further
    specificity-judge call re-confirming a verdict it already computed --
    it halts immediately on this round's verdict instead of looping."""
    bad_draft = _draft(
        why_people_care=BriefFieldDraft(content="Fans wanted the reunion.", citations=[])
    )
    brief = compose_topic_brief(bad_draft)
    state = _state(GATHERED_URLS)

    # Only ONE verdict queued -- a second check_brief() call (which would pop
    # a second verdict) would raise IndexError, so this also proves no
    # further specificity-judge call happens.
    fake_llm = FakeSpecificityLLM([_all_specific_verdict()])
    fake_agent = RefusedFakeContextAgent([(GATHERED_URLS, bad_draft)])

    outcome = check_and_repair_brief("Wistoria", brief, state, fake_agent, fake_llm, db)

    assert len(fake_agent.calls) == 1  # the refused reenter itself still fires once
    assert fake_llm.call_count == 1  # no 2nd specificity-judge call after the refusal
    assert outcome.halted is True
    assert outcome.rounds_used == 0  # the refused round was never counted as completed
    assert outcome.brief.why_people_care.verified is False
    assert outcome.brief.identity.verified is True

    persisted = load_topic_brief("Wistoria", db)
    assert persisted is not None
    assert persisted.why_people_care.verified is False


def test_caps_are_not_reset_by_repair_rounds(db):
    """AC10: check_and_repair_brief adds no budget of its own -- it only ever
    calls context_agent.reenter_with_query, which (per ticket 02) is what
    enforces the existing run-level caps cumulatively. This test proves the
    checker never reads/writes any cap itself by asserting the state object
    threaded into reenter_with_query is exactly the one the prior round
    returned (never reconstructed with reset counters)."""
    bad_draft = _draft(
        why_people_care=BriefFieldDraft(content="Fans wanted the reunion.", citations=[])
    )
    brief = compose_topic_brief(bad_draft)
    state = _state(GATHERED_URLS)

    class CapAwareFakeAgent(FakeContextAgent):
        def reenter_with_query(self, state, action, query):
            # A real ContextAgent would refuse to run if caps were already
            # exhausted; this fake just proves the SAME state flows through
            # unmodified rather than a fresh one with caps reset to zero.
            assert state.reddit_calls == 1 and state.tavily_calls == 1
            return super().reenter_with_query(state, action, query)

    fake_llm = FakeSpecificityLLM([_all_specific_verdict()] * 2)
    fake_agent = CapAwareFakeAgent([(GATHERED_URLS, _draft())])

    outcome = check_and_repair_brief("Wistoria", brief, state, fake_agent, fake_llm, db)

    assert outcome.halted is False
    assert outcome.rounds_used == 1
