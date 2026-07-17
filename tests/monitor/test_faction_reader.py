"""Tests for the Faction Map reader stage + persistence (Exilus ticket 05).

Per the PRD's Testing Decisions, these assert external artifact shape/content
and control flow only (map shape, camp count, stamp presence, whether/how-many
top-up calls fired) -- never internal prompt wording or call order. The LLM
and the top-up ``reddit_search``'s ``item_fetcher`` are both fakes/injected
seams; the DB session is the same sqlite-in-memory fixture ticket 01's tests
use (no pgvector column on this table, so a real Postgres connection buys
nothing here).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.exilus_topic import ExilusTopicRecord
from src.monitor.faction_reader import (
    FactionEmergenceError,
    FactionReader,
    load_faction_map,
    save_faction_map,
)
from src.monitor.schemas import Camp, EvidenceQuote, FactionMap, FactionMapDraft


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


class FakeLLM:
    """Returns a queued FactionMapDraft per _emerge_camps call, in order."""

    def __init__(self, drafts: list[FactionMapDraft]) -> None:
        self._drafts = list(drafts)
        self.call_count = 0
        self.last_prompt = ""

    def parse(self, prompt: str, response_model: type, **kwargs) -> FactionMapDraft:
        self.call_count += 1
        self.last_prompt = prompt
        return self._drafts.pop(0)


def _camp(name: str, weight: float) -> Camp:
    return Camp(
        name=name,
        feeling="hopeful",
        surface_want=f"{name} wants X",
        deeper_desire=f"{name} secretly wants Y",
        evidence_quotes=[EvidenceQuote(quote="I wish they did X", upvotes=42)],
        weight=weight,
    )


def _reddit_text(n_comments: int) -> str:
    """Build gathered reddit text with exactly ``n_comments`` surviving comments."""
    lines = ["[POST | 100 upvotes] Some thread title"]
    lines += [f"  [COMMENT | 10 upvotes] comment body {i}" for i in range(n_comments)]
    return "\n".join(lines)


def _make_item_fetcher(n_extra_comments: int, calls: list[dict]):
    """Fake item_fetcher: records each run_input and returns one post plus
    ``n_extra_comments`` surviving (score=10 >= 5) comments in the actor's
    raw item shape, so a real reddit_search() call on top of it accumulates
    exactly that many additional surviving comments.
    """

    def fetch(run_input: dict) -> list[dict]:
        calls.append(run_input)
        items = [{"dataType": "post", "id": "p1", "score": 99, "title": "t", "postUrl": "https://reddit.com/p1"}]
        items += [
            {"dataType": "comment", "postId": "p1", "score": 10, "body": f"extra {i}"}
            for i in range(n_extra_comments)
        ]
        return items

    return fetch


# ---------------------------------------------------------------------------
# Camp cap + single-camp acceptance (AC1)
# ---------------------------------------------------------------------------


def test_camp_cap_applied_post_emergence():
    """AC1: an LLM emitting 7 camps is capped to 5, kept by weight descending."""
    camps = [_camp(f"camp{i}", weight=i / 10) for i in range(7)]
    draft = FactionMapDraft(camps=camps)
    fake = FakeLLM([draft])
    reader = FactionReader(llm=fake)

    result = reader.read("Wistoria", _reddit_text(30))

    assert len(result.camps) == 5
    weights = [c.weight for c in result.camps]
    assert weights == sorted(weights, reverse=True)
    assert weights[0] == pytest.approx(0.6)  # camp6, the highest weight


def test_single_camp_map_accepted():
    """AC1: a unanimous audience (one emerged camp) is legal, not padded or rejected."""
    draft = FactionMapDraft(camps=[_camp("unanimous", weight=1.0)])
    fake = FakeLLM([draft])
    reader = FactionReader(llm=fake)

    result = reader.read("Wistoria", _reddit_text(30))

    assert len(result.camps) == 1
    assert result.camps[0].name == "unanimous"


def test_camp_fields_shape():
    """AC2: each camp carries name/feeling/surface_want/deeper_desire/evidence_quotes/weight,
    and evidence_quotes pair each quote with its upvote count."""
    draft = FactionMapDraft(camps=[_camp("solo", weight=1.0)])
    fake = FakeLLM([draft])
    reader = FactionReader(llm=fake)

    result = reader.read("Wistoria", _reddit_text(30))
    camp = result.camps[0]

    assert camp.name == "solo"
    assert camp.surface_want != camp.deeper_desire
    assert camp.evidence_quotes[0].quote == "I wish they did X"
    assert camp.evidence_quotes[0].upvotes == 42


# ---------------------------------------------------------------------------
# Top-up control flow (AC3-5)
# ---------------------------------------------------------------------------


def test_at_or_above_floor_makes_zero_topup_calls():
    """AC3: at/above the ~30 floor, zero additional reddit_search/item_fetcher calls."""
    calls: list[dict] = []
    fetcher = _make_item_fetcher(n_extra_comments=0, calls=calls)
    draft = FactionMapDraft(camps=[_camp("solo", weight=1.0)])
    fake = FakeLLM([draft])
    reader = FactionReader(llm=fake, item_fetcher=fetcher)

    result = reader.read("Wistoria", _reddit_text(30))

    assert calls == []
    assert result.thin_data is False


def test_below_floor_triggers_exactly_one_topup_call():
    """AC4: below the floor, exactly one additional scoped reddit_search call fires."""
    calls: list[dict] = []
    fetcher = _make_item_fetcher(n_extra_comments=20, calls=calls)
    draft = FactionMapDraft(camps=[_camp("solo", weight=1.0)])
    fake = FakeLLM([draft])
    reader = FactionReader(llm=fake, item_fetcher=fetcher)

    reader.read("Wistoria", _reddit_text(10))  # 10 < 30 floor

    assert len(calls) == 1


def test_topup_still_short_stamps_thin_data_and_makes_no_second_call():
    """AC5: topped-up volume still below floor -> thin_data=True, never a 2nd top-up call."""
    calls: list[dict] = []
    fetcher = _make_item_fetcher(n_extra_comments=5, calls=calls)  # 10 + 5 = 15, still < 30
    draft = FactionMapDraft(camps=[_camp("solo", weight=1.0)])
    fake = FakeLLM([draft])
    reader = FactionReader(llm=fake, item_fetcher=fetcher)

    result = reader.read("Wistoria", _reddit_text(10))

    assert len(calls) == 1  # never a 2nd top-up, even though still short
    assert result.thin_data is True


def test_topup_brings_volume_above_floor_no_thin_data_stamp():
    """AC5 (converse): topped-up volume clears the floor -> no THIN DATA stamp."""
    calls: list[dict] = []
    fetcher = _make_item_fetcher(n_extra_comments=25, calls=calls)  # 10 + 25 = 35 >= 30
    draft = FactionMapDraft(camps=[_camp("solo", weight=1.0)])
    fake = FakeLLM([draft])
    reader = FactionReader(llm=fake, item_fetcher=fetcher)

    result = reader.read("Wistoria", _reddit_text(10))

    assert len(calls) == 1
    assert result.thin_data is False


def test_topup_skipped_when_cumulative_run_budget_exhausted():
    """FIX 5: below the floor, but ``spent_so_far`` plus the top-up's own
    estimated cost would exceed the run's cumulative Apify cap -> the
    top-up is skipped entirely (zero item_fetcher calls), straight to
    THIN DATA. The per-call $1 guard alone would have let this call
    through -- this proves the CUMULATIVE run budget is what's actually
    checked, not just the single-call guard."""
    calls: list[dict] = []
    fetcher = _make_item_fetcher(n_extra_comments=25, calls=calls)
    draft = FactionMapDraft(camps=[_camp("solo", weight=1.0)])
    fake = FakeLLM([draft])
    reader = FactionReader(llm=fake, item_fetcher=fetcher)

    # The topup's own estimated cost is ~$0.23 (reddit_search's defaults);
    # 0.80 + 0.23 > the $1.00 cumulative cap.
    result = reader.read("Wistoria", _reddit_text(10), spent_so_far=0.80)

    assert calls == []  # top-up never fired
    assert result.thin_data is True


def test_topup_runs_when_cumulative_run_budget_has_room():
    """FIX 5, converse: spent_so_far leaves enough headroom for the top-up's
    own estimated cost -> the top-up still fires exactly once, unchanged
    from AC4's existing behavior."""
    calls: list[dict] = []
    fetcher = _make_item_fetcher(n_extra_comments=25, calls=calls)
    draft = FactionMapDraft(camps=[_camp("solo", weight=1.0)])
    fake = FakeLLM([draft])
    reader = FactionReader(llm=fake, item_fetcher=fetcher)

    result = reader.read("Wistoria", _reddit_text(10), spent_so_far=0.10)

    assert len(calls) == 1
    assert result.thin_data is False


# ---------------------------------------------------------------------------
# Zero-camp emergence: bounded retry then raise (FIX 7, mirrors ideation.py's
# D7 convention -- FactionMap.camps has min_length=1).
# ---------------------------------------------------------------------------


def test_zero_camps_retried_once_then_succeeds():
    """A first emergence call returning zero camps gets exactly one retry;
    a non-empty second draft composes normally."""
    fake = FakeLLM([FactionMapDraft(camps=[]), FactionMapDraft(camps=[_camp("solo", weight=1.0)])])
    reader = FactionReader(llm=fake)

    result = reader.read("Wistoria", _reddit_text(30))

    assert fake.call_count == 2
    assert len(result.camps) == 1
    assert result.camps[0].name == "solo"


def test_zero_camps_after_retry_raises():
    """A draft still empty after the one bounded retry raises
    FactionEmergenceError rather than composing an invalid empty FactionMap."""
    fake = FakeLLM([FactionMapDraft(camps=[]), FactionMapDraft(camps=[])])
    reader = FactionReader(llm=fake)

    with pytest.raises(FactionEmergenceError):
        reader.read("Wistoria", _reddit_text(30))

    assert fake.call_count == 2  # exactly 1 retry, no 3rd call


# ---------------------------------------------------------------------------
# No-network default test run (AC6) -- covered implicitly by every test above
# using an injected FakeLLM + item_fetcher, no real network/Apify call. This
# test pins that a call above the floor works with NO item_fetcher at all
# (the no-top-up path never even needs the seam).
# ---------------------------------------------------------------------------


def test_above_floor_needs_no_item_fetcher_at_all():
    draft = FactionMapDraft(camps=[_camp("solo", weight=1.0)])
    fake = FakeLLM([draft])
    reader = FactionReader(llm=fake)  # item_fetcher intentionally omitted

    result = reader.read("Wistoria", _reddit_text(30))

    assert result.thin_data is False


# ---------------------------------------------------------------------------
# Persistence (AC8-9)
# ---------------------------------------------------------------------------


def _map(marker: str) -> FactionMap:
    return FactionMap(
        camps=[_camp(f"camp-{marker}", weight=1.0)],
        thin_data=False,
    )


def test_save_and_load_round_trips_equal_map(db):
    faction_map = _map("v1")

    save_faction_map("Elfaria: Albis & Serfort", faction_map, db)
    fetched = load_faction_map("Elfaria: Albis & Serfort", db)

    assert fetched == faction_map


def test_second_save_replaces_rather_than_stacks(db):
    save_faction_map("refresh-topic", _map("v1"), db)
    save_faction_map("refresh-topic", _map("v2"), db)

    fetched = load_faction_map("refresh-topic", db)

    assert fetched.camps[0].name == "camp-v2"
    assert db.query(ExilusTopicRecord).filter_by(topic="refresh-topic").count() == 1


def test_load_unseen_topic_returns_none(db):
    assert load_faction_map("never-researched", db) is None


def test_load_topic_row_with_no_faction_map_yet_returns_none(db):
    row = ExilusTopicRecord(topic="brief-only-topic")
    db.add(row)
    db.commit()

    assert load_faction_map("brief-only-topic", db) is None
