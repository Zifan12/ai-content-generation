"""Orchestration tests for scripts/exilus.py run_exilus_pipeline (Exilus ticket 07).

Mirrors tests/monitor/test_pitch_angles.py's style (fakes for every injected
component, assertions on call lists/counts, persisted rows, and handoff JSON
content) applied to the Exilus lane's four stages: research (ContextAgent) ->
checker + bounded repair (the REAL brief_checker.check_and_repair_brief,
fed fakes) -> faction read (FactionReader) -> ideation (Ideator).
"""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.exilus as exilus_module
from scripts.exilus import (
    dump_artifacts,
    import_artifacts,
    run_exilus_pipeline,
)
from src.database import Base
from src.models.angle_pitch import AnglePitchRecord
from src.models.trending_event import TrendingEventRecord
from src.monitor.context_agent import ContextAgentState
from src.monitor.faction_reader import load_faction_map, save_faction_map
from src.monitor.schemas import (
    BriefField,
    Camp,
    CharacterRef,
    ContentMode,
    ContextBundle,
    EvidenceQuote,
    ExilusIdea,
    ExilusSlate,
    FactionMap,
    TopicBrief,
)
from src.monitor.topic_brief import load_topic_brief, save_topic_brief

TOPIC = "Wistoria fans imagining Elfaria and Serfort's reunion"

GATHERED_URLS = ["https://reddit.com/r/x/comments/1", "https://example.com/article"]


class CallLog:
    """Shared event log every fake below appends its name to, so tests can
    assert both WHICH stages ran and in what ORDER (AC1)."""

    def __init__(self) -> None:
        self.events: list[str] = []


def _brief_field(content: str = "content", verified: bool = True) -> BriefField:
    return BriefField(content=content, citations=[GATHERED_URLS[0]], verified=verified)


def _brief() -> TopicBrief:
    return TopicBrief(
        identity=_brief_field("Wistoria is a fantasy anime."),
        recent_events=_brief_field("Season 2 finale aired June 28."),
        key_characters=_brief_field("Elfaria and Will/Serfort are the pair."),
        why_people_care=_brief_field("Fans wanted the reunion."),
        open_unknowns=[],
    )


def _camp(name: str, weight: float = 0.5) -> Camp:
    return Camp(
        name=name,
        feeling="hopeful",
        surface_want="wants a reunion on screen",
        deeper_desire="wants proof the years apart still mattered",
        evidence_quotes=[EvidenceQuote(quote="please just let them reunite", upvotes=80)],
        weight=weight,
    )


def _faction_map(*camp_names: str) -> FactionMap:
    n = len(camp_names)
    return FactionMap(camps=[_camp(name, weight=1.0 / n) for name in camp_names])


def _idea(logline: str, target_camp: str) -> ExilusIdea:
    return ExilusIdea(
        logline=logline,
        mode=ContentMode.wish,
        characters=[CharacterRef(name="Elfaria", ip_source="Wistoria")],
        desired_moment="Elfaria and Serfort finally embrace",
        why_it_lands="delivers the reunion fans have waited for",
        legal_flag=False,
        target_camp=target_camp,
    )


def _slate(*loglines: str, target_camp: str = "the reunion romantics") -> ExilusSlate:
    """Build an ExilusSlate (min_length=8) with ``loglines`` first, in order,
    padded with filler ideas so index-based test assertions (e.g. choice "1"
    -> the first named logline) still land on the exact idea a test names."""
    ideas = [_idea(line, target_camp) for line in loglines]
    filler_needed = max(0, 8 - len(ideas))
    ideas.extend(
        _idea(f"filler idea {i}", target_camp) for i in range(filler_needed)
    )
    return ExilusSlate(ideas=ideas)


def _state() -> ContextAgentState:
    return ContextAgentState(
        topic=TOPIC,
        reddit_text="[COMMENT | 10 upvotes] please just let them reunite",
        web_text="raw web text",
        reddit_calls=1,
        tavily_calls=1,
        apify_cost_estimate=0.05,
        within_community="",
        next_action="stop",
        next_query="",
        urls=GATHERED_URLS,
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )


def _bundle() -> ContextBundle:
    return ContextBundle(
        reaction_sample="please just let them reunite",
        summary="fans want a reunion",
        key_moments=[],
        references=GATHERED_URLS,
        sources=["reddit_search", "tavily_search"],
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


class FakeContextAgent:
    """gather_brief() returns a fixed (brief, bundle, web_text, state) once;
    reenter_with_query() replays queued (urls, brief) repairs, in order."""

    def __init__(
        self,
        log: CallLog,
        brief: TopicBrief | None = None,
        repaired: list[tuple[list[str], TopicBrief]] | None = None,
    ) -> None:
        self.log = log
        self._brief = brief if brief is not None else _brief()
        self._repaired = list(repaired) if repaired is not None else []
        self.gather_calls: list[str] = []
        self.reenter_calls: list[tuple[str, str]] = []

    def gather_brief(self, topic: str):
        self.log.events.append("gather_brief")
        self.gather_calls.append(topic)
        return self._brief, _bundle(), "raw web text", _state()

    def reenter_with_query(self, state, action, query):
        self.log.events.append("reenter_with_query")
        self.reenter_calls.append((action, query))
        urls, draft_brief = self._repaired.pop(0)
        # brief_checker composes from state.brief_draft via compose_topic_brief;
        # the fake short-circuits that composition by handing the checker's
        # caller a state whose already-composed brief the test controls
        # directly via a monkeypatched compose (see _make_repair_state below).
        # tavily_calls +1 models "real progress happened" this round (FIX 6's
        # no-new-tool-calls refusal check in check_and_repair_brief) -- a
        # real repair round's forced action always targets tavily_search.
        return state.model_copy(
            update={
                "urls": urls,
                "brief_draft": _draft_for(draft_brief),
                "tavily_calls": state.tavily_calls + 1,
            }
        )


def _draft_for(brief: TopicBrief):
    """Build a TopicBriefDraft carrying the same content as ``brief`` — the
    round-trip compose_topic_brief() performs inside check_and_repair_brief."""
    from src.monitor.schemas import BriefFieldDraft, TopicBriefDraft

    def _fd(field: BriefField) -> BriefFieldDraft:
        return BriefFieldDraft(content=field.content, citations=field.citations)

    return TopicBriefDraft(
        identity=_fd(brief.identity),
        recent_events=_fd(brief.recent_events),
        key_characters=_fd(brief.key_characters),
        why_people_care=_fd(brief.why_people_care),
        open_unknowns=brief.open_unknowns,
    )


class FakeSpecificityLLM:
    """Returns queued verdicts in order — the specificity-layer LLM."""

    def __init__(self, log: CallLog, verdicts: list) -> None:
        self.log = log
        self._verdicts = list(verdicts)

    def parse(self, prompt, response_model, **kwargs):
        self.log.events.append("specificity")
        return self._verdicts.pop(0)


def _all_specific():
    from src.monitor.brief_checker import SpecificityVerdict

    return SpecificityVerdict(
        reasoning="every field is concrete",
        identity_specific=True,
        recent_events_specific=True,
        key_characters_specific=True,
        why_people_care_specific=True,
    )


class FakeFactionReader:
    def __init__(self, log: CallLog, faction_map: FactionMap | None = None) -> None:
        self.log = log
        self._faction_map = faction_map if faction_map is not None else _faction_map(
            "the reunion romantics"
        )
        self.calls: list[tuple[str, str, float]] = []

    def read(self, topic: str, reddit_text: str, spent_so_far: float = 0.0) -> FactionMap:
        self.log.events.append("faction_read")
        self.calls.append((topic, reddit_text, spent_so_far))
        return self._faction_map


class FakeIdeator:
    def __init__(self, log: CallLog, slate: ExilusSlate | None = None) -> None:
        self.log = log
        self._slate = slate if slate is not None else _slate("idea one", "idea two")
        self.calls: list[tuple[TopicBrief, FactionMap, tuple[str, ...]]] = []

    def generate(self, brief, faction_map, prior_loglines=()):
        self.log.events.append("ideation")
        self.calls.append((brief, faction_map, prior_loglines))
        return self._slate


class _RecordingReplace:
    """Stand-in for fridge.replace_topic_material — sqlite can't run pgvector."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, topic, web_text, reddit_text, embedder, session) -> int:
        self.calls.append((topic, web_text, reddit_text))
        return 1


_SENTINEL_EMBEDDER = object()


def pick_first() -> str:
    return "1"


# ---------------------------------------------------------------------------
# AC1/AC3: fresh topic runs every stage, in order, and a passing brief flows
# through with no blocking prompt.
# ---------------------------------------------------------------------------


def test_fresh_topic_runs_all_stages_in_order(db, tmp_path, monkeypatch):
    monkeypatch.setattr(exilus_module, "replace_topic_material", _RecordingReplace())
    log = CallLog()
    context_agent = FakeContextAgent(log)
    specificity_llm = FakeSpecificityLLM(log, [_all_specific()])
    faction_reader = FakeFactionReader(log)
    ideator = FakeIdeator(log)

    handoff = run_exilus_pipeline(
        db,
        context_agent,
        specificity_llm,
        faction_reader,
        ideator,
        _SENTINEL_EMBEDDER,
        topic=TOPIC,
        refresh=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    assert log.events == ["gather_brief", "specificity", "faction_read", "ideation"]
    assert handoff is not None
    # Artifacts pinned for next time.
    assert load_topic_brief(TOPIC, db) is not None
    assert load_faction_map(TOPIC, db) is not None


# ---------------------------------------------------------------------------
# AC2: UNVERIFIED + halt — checker exhausts its repair budget, faction/
# ideation never run, no slate ever printed/offered.
# ---------------------------------------------------------------------------


def test_unverified_halt_stops_before_faction_and_ideation(db, tmp_path, monkeypatch):
    replace_recorder = _RecordingReplace()
    monkeypatch.setattr(exilus_module, "replace_topic_material", replace_recorder)
    log = CallLog()

    bad_brief = _brief()
    bad_brief.why_people_care = BriefField(content="Fans wanted the reunion.", citations=[])

    # Every repair round hands back the same unresolved gap (citation-less
    # field never gets fixed) — forces exactly 2 rounds then halt.
    context_agent = FakeContextAgent(
        log,
        brief=bad_brief,
        repaired=[(GATHERED_URLS, bad_brief), (GATHERED_URLS, bad_brief)],
    )
    specificity_llm = FakeSpecificityLLM(log, [_all_specific()] * 3)
    faction_reader = FakeFactionReader(log)
    ideator = FakeIdeator(log)

    handoff = run_exilus_pipeline(
        db,
        context_agent,
        specificity_llm,
        faction_reader,
        ideator,
        _SENTINEL_EMBEDDER,
        topic=TOPIC,
        refresh=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    assert handoff is None
    assert len(context_agent.reenter_calls) == 2  # exactly 2 repair rounds
    assert "faction_read" not in log.events
    assert "ideation" not in log.events
    assert faction_reader.calls == []
    assert ideator.calls == []
    assert db.query(AnglePitchRecord).count() == 0  # no slate ever persisted

    # FIX 4: the research gathered before the halt is still indexed into the
    # fridge -- an UNVERIFIED halt must not throw away the material it just
    # spent budget gathering.
    assert len(replace_recorder.calls) == 1

    persisted = load_topic_brief(TOPIC, db)
    assert persisted is not None
    assert persisted.why_people_care.verified is False
    assert persisted.identity.verified is True


# ---------------------------------------------------------------------------
# AC4/AC5: a pinned re-roll skips research/checker/faction, calls only
# ideation, and threads prior loglines as do-not-repeat.
# ---------------------------------------------------------------------------


def test_pinned_reroll_skips_research_checker_faction(db, tmp_path, monkeypatch):
    replace_recorder = _RecordingReplace()
    monkeypatch.setattr(exilus_module, "replace_topic_material", replace_recorder)

    pinned_brief = _brief()
    pinned_faction = _faction_map("the reunion romantics")
    save_topic_brief(TOPIC, pinned_brief, db)
    save_faction_map(TOPIC, pinned_faction, db)

    log = CallLog()
    context_agent = FakeContextAgent(log)
    specificity_llm = FakeSpecificityLLM(log, [])
    faction_reader = FakeFactionReader(log)
    ideator = FakeIdeator(log, slate=_slate("brand new idea"))

    handoff = run_exilus_pipeline(
        db,
        context_agent,
        specificity_llm,
        faction_reader,
        ideator,
        _SENTINEL_EMBEDDER,
        topic=TOPIC,
        refresh=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    assert log.events == ["ideation"]
    assert context_agent.gather_calls == []
    assert faction_reader.calls == []
    assert replace_recorder.calls == []
    assert handoff is not None
    # ideator received the PINNED artifacts (identity-check by content).
    used_brief, used_faction, _ = ideator.calls[0]
    assert used_brief.identity.content == pinned_brief.identity.content
    assert used_faction.camps[0].name == "the reunion romantics"


# ---------------------------------------------------------------------------
# FIX 3: a verified, pinned brief with NO faction map yet (e.g. an operator
# corrected an UNVERIFIED brief via --import-artifacts, which pins only the
# brief) resumes directly at faction-read -- research/checker never re-run.
# ---------------------------------------------------------------------------


def test_verified_brief_no_faction_map_resumes_at_faction_read(db, tmp_path, monkeypatch):
    replace_recorder = _RecordingReplace()
    monkeypatch.setattr(exilus_module, "replace_topic_material", replace_recorder)

    corrected_brief = _brief()  # every field verified=True, as _brief_field defaults
    save_topic_brief(TOPIC, corrected_brief, db)
    # Deliberately no save_faction_map call -- this topic has never had a
    # faction map pinned.

    log = CallLog()
    context_agent = FakeContextAgent(log)
    specificity_llm = FakeSpecificityLLM(log, [])
    faction_reader = FakeFactionReader(log)
    ideator = FakeIdeator(log)

    handoff = run_exilus_pipeline(
        db,
        context_agent,
        specificity_llm,
        faction_reader,
        ideator,
        _SENTINEL_EMBEDDER,
        topic=TOPIC,
        refresh=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    # Research/checker never re-run -- only faction-read and ideation.
    assert log.events == ["faction_read", "ideation"]
    assert context_agent.gather_calls == []
    assert context_agent.reenter_calls == []
    assert replace_recorder.calls == []  # no new research to index

    assert len(faction_reader.calls) == 1
    called_topic, called_reddit_text, called_spent = faction_reader.calls[0]
    assert called_topic == TOPIC
    assert called_reddit_text == ""  # no cached research state to resume from
    assert called_spent == 0.0

    assert handoff is not None
    used_brief, _, _ = ideator.calls[0]
    assert used_brief.identity.content == corrected_brief.identity.content
    # The faction map read during this resume is now pinned for next time.
    assert load_faction_map(TOPIC, db) is not None


def test_unverified_brief_with_faction_map_still_triggers_research(db, tmp_path, monkeypatch):
    """The converse of FIX 3: an UNVERIFIED brief must still trigger a fresh
    research/checker pass even if a (now-stale) faction map happens to be
    pinned -- only a fully-verified brief may skip research."""
    monkeypatch.setattr(exilus_module, "replace_topic_material", _RecordingReplace())

    unverified_brief = _brief()
    unverified_brief.why_people_care = BriefField(
        content="unclear", citations=[], verified=False
    )
    save_topic_brief(TOPIC, unverified_brief, db)
    save_faction_map(TOPIC, _faction_map("stale camp"), db)

    log = CallLog()
    context_agent = FakeContextAgent(log)
    specificity_llm = FakeSpecificityLLM(log, [_all_specific()])
    faction_reader = FakeFactionReader(log)
    ideator = FakeIdeator(log)

    run_exilus_pipeline(
        db,
        context_agent,
        specificity_llm,
        faction_reader,
        ideator,
        _SENTINEL_EMBEDDER,
        topic=TOPIC,
        refresh=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    assert log.events == ["gather_brief", "specificity", "faction_read", "ideation"]
    assert context_agent.gather_calls == [TOPIC]


def test_reroll_excludes_previously_shown_ideas(db, tmp_path):
    """AC5: prior loglines for this topic are threaded as do-not-repeat, and
    a fake ideator that respects them naturally excludes them from the
    returned slate."""
    save_topic_brief(TOPIC, _brief(), db)
    save_faction_map(TOPIC, _faction_map("the reunion romantics"), db)

    # Simulate a PRIOR run's persisted ideas for this topic's event.
    event = TrendingEventRecord(
        run_at=datetime.now(timezone.utc),
        source="manual",
        headline=TOPIC,
        reaction_sample="",
        trendiness_score=0.0,
        virality_window_hours=24.0,
    )
    db.add(event)
    db.flush()
    db.add(
        AnglePitchRecord(
            trending_event_id=event.id,
            take="already shown idea",
            estimated_cost_credits=0.0,
            gap_satisfaction_rationale="x",
            legal_flag=False,
            approved=None,
            idea_json={},
            mode="wish",
        )
    )
    db.commit()

    log = CallLog()
    ideator = FakeIdeator(log, slate=_slate("a genuinely new idea"))

    run_exilus_pipeline(
        db,
        FakeContextAgent(log),
        FakeSpecificityLLM(log, []),
        FakeFactionReader(log),
        ideator,
        _SENTINEL_EMBEDDER,
        topic=TOPIC,
        refresh=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    _, _, prior_loglines = ideator.calls[0]
    assert prior_loglines == ("already shown idea",)
    returned_loglines = [idea.logline for idea in ideator._slate.ideas]
    assert "already shown idea" not in returned_loglines


# ---------------------------------------------------------------------------
# AC6: --refresh re-runs everything regardless of pinned state and REPLACES
# stored artifacts + fridge rows.
# ---------------------------------------------------------------------------


def test_refresh_reruns_and_replaces(db, tmp_path, monkeypatch):
    replace_recorder = _RecordingReplace()
    monkeypatch.setattr(exilus_module, "replace_topic_material", replace_recorder)

    old_brief = _brief()
    old_brief.identity = BriefField(content="OLD identity", citations=[GATHERED_URLS[0]])
    old_faction = _faction_map("old camp")
    save_topic_brief(TOPIC, old_brief, db)
    save_faction_map(TOPIC, old_faction, db)

    new_brief = _brief()
    new_brief.identity = BriefField(content="NEW identity", citations=[GATHERED_URLS[0]])

    log = CallLog()
    context_agent = FakeContextAgent(log, brief=new_brief)
    specificity_llm = FakeSpecificityLLM(log, [_all_specific()])
    faction_reader = FakeFactionReader(log, faction_map=_faction_map("new camp"))
    ideator = FakeIdeator(log)

    run_exilus_pipeline(
        db,
        context_agent,
        specificity_llm,
        faction_reader,
        ideator,
        _SENTINEL_EMBEDDER,
        topic=TOPIC,
        refresh=True,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    assert log.events == ["gather_brief", "specificity", "faction_read", "ideation"]
    assert len(replace_recorder.calls) == 1  # fridge replaced, not appended-to

    # A read after the refresh returns only the NEW content.
    reloaded_brief = load_topic_brief(TOPIC, db)
    assert reloaded_brief.identity.content == "NEW identity"
    reloaded_faction = load_faction_map(TOPIC, db)
    assert reloaded_faction.camps[0].name == "new camp"


# ---------------------------------------------------------------------------
# AC7/AC8: pick persists + hands off; skip/invalid persists but hands off
# nothing.
# ---------------------------------------------------------------------------


def test_approved_pick_persists_and_hands_off(db, tmp_path, monkeypatch):
    monkeypatch.setattr(exilus_module, "replace_topic_material", _RecordingReplace())
    log = CallLog()
    slate = _slate("idea A", "idea B", target_camp="the reunion romantics")
    ideator = FakeIdeator(log, slate=slate)

    handoff = run_exilus_pipeline(
        db,
        FakeContextAgent(log),
        FakeSpecificityLLM(log, [_all_specific()]),
        FakeFactionReader(log),
        ideator,
        _SENTINEL_EMBEDDER,
        topic=TOPIC,
        refresh=False,
        choice_provider=lambda: "1",
        output_dir=tmp_path,
    )

    assert handoff is not None
    approved = db.query(AnglePitchRecord).filter_by(approved=True).one()
    assert approved.take == "idea A"
    assert approved.idea_json is not None
    assert approved.story_json is None  # StoryArchitect out of scope for this ticket
    unpicked_takes = {
        row.take for row in db.query(AnglePitchRecord).filter_by(approved=None).all()
    }
    assert "idea B" in unpicked_takes

    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text())
    assert data["pitch_id"] == approved.id
    assert data["logline"] == "idea A"
    assert data["mode"] == "wish"
    assert data["target_camp"] == "the reunion romantics"
    assert "story" not in data  # no developed script exists at this stage


def test_skip_persists_slate_but_writes_no_handoff(db, tmp_path, monkeypatch):
    monkeypatch.setattr(exilus_module, "replace_topic_material", _RecordingReplace())
    log = CallLog()

    handoff = run_exilus_pipeline(
        db,
        FakeContextAgent(log),
        FakeSpecificityLLM(log, [_all_specific()]),
        FakeFactionReader(log),
        FakeIdeator(log),
        _SENTINEL_EMBEDDER,
        topic=TOPIC,
        refresh=False,
        choice_provider=lambda: "s",
        output_dir=tmp_path,
    )

    assert handoff is None
    assert db.query(AnglePitchRecord).count() == 8  # slate saved (default fake slate)
    assert db.query(AnglePitchRecord).filter_by(approved=True).count() == 0
    assert len(list(tmp_path.glob("*.json"))) == 0


def test_invalid_selection_persists_slate_but_writes_no_handoff(db, tmp_path, monkeypatch):
    monkeypatch.setattr(exilus_module, "replace_topic_material", _RecordingReplace())
    log = CallLog()

    handoff = run_exilus_pipeline(
        db,
        FakeContextAgent(log),
        FakeSpecificityLLM(log, [_all_specific()]),
        FakeFactionReader(log),
        FakeIdeator(log),
        _SENTINEL_EMBEDDER,
        topic=TOPIC,
        refresh=False,
        choice_provider=lambda: "99",
        output_dir=tmp_path,
    )

    assert handoff is None
    assert db.query(AnglePitchRecord).filter_by(approved=True).count() == 0
    assert len(list(tmp_path.glob("*.json"))) == 0


# ---------------------------------------------------------------------------
# dump/import artifacts (US22)
# ---------------------------------------------------------------------------


def test_dump_then_import_round_trips_artifacts(db, tmp_path):
    brief = _brief()
    faction = _faction_map("the reunion romantics")
    save_topic_brief(TOPIC, brief, db)
    save_faction_map(TOPIC, faction, db)

    brief_path, faction_path = dump_artifacts(TOPIC, db, tmp_path)
    assert brief_path is not None and brief_path.exists()
    assert faction_path is not None and faction_path.exists()

    # Edit the dumped brief, like an operator would.
    data = json.loads(brief_path.read_text())
    data["identity"]["content"] = "hand-edited identity"
    brief_path.write_text(json.dumps(data))

    brief_ok, faction_ok = import_artifacts(TOPIC, db, tmp_path)
    assert brief_ok is True
    assert faction_ok is True

    reloaded = load_topic_brief(TOPIC, db)
    assert reloaded.identity.content == "hand-edited identity"


def test_dump_skips_missing_artifacts(db, tmp_path):
    brief_path, faction_path = dump_artifacts(TOPIC, db, tmp_path)
    assert brief_path is None
    assert faction_path is None
