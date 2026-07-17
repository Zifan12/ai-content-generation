"""Orchestration tests for scripts/pitch_angles.py run_pitch_pipeline.

Slice ① (staged director, 2026-07-16): the pitcher emits a desire-only
IdeaPitchSlate; the human picks ONE idea; only the picked idea is developed
by the StoryArchitect into a StoryScript, which the craft gate + dialogue
floor (+ Path B grounding) judge with one bounded repair each. Unpicked
ideas persist with idea_json only (story_json NULL).
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.pitch_angles as pitch_angles_module
from scripts.pitch_angles import run_pitch_pipeline
from src.database import Base
from src.models.angle_pitch import AnglePitchRecord
from src.models.trending_event import TrendingEventRecord
from src.monitor.pitch_grounding import GroundingVerdict
from src.monitor.schemas import (
    BeatRole,
    CharacterRef,
    ContentMode,
    ContextBundle,
    GapAnalysis,
    IdeaFitResult,
    IdeaPitch,
    IdeaPitchSlate,
    ShotSize,
    StoryBeat,
    StoryCraftVerdict,
    StoryScript,
    TrendingEvent,
)

# ---------------------------------------------------------------------------
# Sample pipeline data (one event -> one gap -> a slate of story IDEAS)
# ---------------------------------------------------------------------------

SAMPLE_EVENT = TrendingEvent(
    headline="Dragon spotted circling Tokyo Tower at dawn",
    subreddit="interestingasfuck",
    url="https://reddit.com/r/interestingasfuck/comments/abc123",
    reaction_sample=(
        "Top comment: 'I wish we got to see it actually breathe fire.' "
        "Reply: 'They cut away right before the good part, classic.'"
    ),
    trendiness_score=0.92,
    virality_window_hours=18.0,
    raw_source_data={},
    origin="scraped",
)

SAMPLE_GAP = GapAnalysis(
    dominant_emotion="longing",
    audience_want="to see the dragon actually breathe fire",
    evidence_quotes=["I wish we got to see it actually breathe fire."],
    reasoning="The crowd was teased a payoff the footage never delivered.",
)


def _idea(
    logline: str,
    *,
    mode: ContentMode = ContentMode.wish,
    legal_flag: bool = False,
    characters: list[CharacterRef] | None = None,
) -> IdeaPitch:
    return IdeaPitch(
        logline=logline,
        mode=mode,
        characters=characters or [CharacterRef(name="Dragon", ip_source="Original")],
        desired_moment="the dragon breathes fire over the tower",
        why_it_lands="Delivers the fire-breath payoff fans were denied.",
        legal_flag=legal_flag,
    )


SAMPLE_SLATE = IdeaPitchSlate(
    ideas=[
        _idea("The dragon finally breathes fire over Tokyo Tower at dawn"),
        _idea("A rooftop crowd watches the dragon's fire erupt", legal_flag=True),
    ]
)


def _beats(cast: list[str] | None = None) -> list[StoryBeat]:
    cast = cast or ["Dragon"]
    return [
        StoryBeat(
            role=BeatRole.hook,
            visual_line="wide aerial of the tower at dawn",
            narration_line=None,
            shot_size=ShotSize.establishing,
            characters_in_frame=cast,
            hero_moment=False,
        ),
        StoryBeat(
            role=BeatRole.build,
            visual_line="the dragon inhales, scales glowing",
            narration_line=None,
            shot_size=ShotSize.medium,
            characters_in_frame=cast,
            hero_moment=False,
        ),
        StoryBeat(
            role=BeatRole.payoff,
            visual_line="fire erupts over the tower",
            narration_line=None,
            shot_size=ShotSize.close_up,
            characters_in_frame=cast,
            hero_moment=True,
        ),
    ]


def _script_for(idea: IdeaPitch, beats: list[StoryBeat] | None = None) -> StoryScript:
    """Compose a script the way the real architect does: idea fields copied."""
    return StoryScript(
        logline=idea.logline,
        mode=idea.mode,
        characters=list(idea.characters),
        desired_moment=idea.desired_moment,
        scene_setting="the tower's rooftop deck at dawn",
        beats=beats or _beats([c.name for c in idea.characters]),
        why_it_lands=idea.why_it_lands,
        legal_flag=idea.legal_flag,
    )


def _passing_verdict() -> StoryCraftVerdict:
    return StoryCraftVerdict(
        clear_desire=True,
        visible_turn=True,
        earned_payoff=True,
        emotion_physical_tell=True,
        cold_viewer_legible=True,
        kinetic_payoff=True,
        register_match=True,
        dialogue_earns_place=True,
        scene_setting_contained=True,
        one_action_per_beat=True,
        notes="clean arc",
        failure_notes=None,
        would_watch=True,
    )


def _failing_verdict() -> StoryCraftVerdict:
    return StoryCraftVerdict(
        clear_desire=True,
        visible_turn=False,
        earned_payoff=False,
        emotion_physical_tell=False,
        cold_viewer_legible=False,
        kinetic_payoff=False,
        register_match=False,
        dialogue_earns_place=False,
        scene_setting_contained=False,
        one_action_per_beat=False,
        notes="no real turn",
        failure_notes="beat 2 needs a real turn",
        would_watch=False,
    )


# Path B (--topic) fixtures — a manual-origin event + a non-empty bundle.
SAMPLE_TOPIC_EVENT = TrendingEvent(
    headline="Wuthering Waves Jinhsi ultimate leaked",
    subreddit="",
    url="https://reddit.com/r/WutheringWavesLeaks/jinhsi",
    reaction_sample="I wish we saw the full cutscene, the leak only showed the burst",
    trendiness_score=0.0,
    virality_window_hours=24.0,
    raw_source_data={"topic": "Wuthering Waves Jinhsi", "sources": ["reddit_search"]},
    origin="manual",
)

SAMPLE_BUNDLE = ContextBundle(
    reaction_sample="I wish we saw the full cutscene; the leak only showed the burst",
    summary="A Wuthering Waves leak teased Jinhsi's ultimate; footage cuts before the full cutscene.",
    key_moments=["leak drop at 06:14", "cutaway before ultimate"],
    references=["https://reddit.com/r/WutheringWavesLeaks/jinhsi"],
    sources=["reddit_search", "tavily_search"],
)

FLAGGED_BUNDLE = ContextBundle(
    reaction_sample="Zeo protecting Will from ending up like that dried up alien",
    summary="Fans are joking about an in-universe bond mechanic; unclear if it's literal.",
    key_moments=[],
    references=[],
    sources=["reddit_search", "tavily_search"],
    unresolved_facts=["whether the 'dried up alien' joke refers to an in-universe life-force-drain mechanic or something else"],
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


class FakeScraper:
    def __init__(self, events: list[TrendingEvent] | None = None) -> None:
        self._events = events if events is not None else [SAMPLE_EVENT]
        self.calls = 0

    def fetch(self) -> list[TrendingEvent]:
        self.calls += 1
        return self._events


class FakeExtractor:
    """Pass-through by default; set ``events`` to force a fixed shortlist."""

    def __init__(self, events: list[TrendingEvent] | None = None) -> None:
        self._events = events
        self.calls = 0

    def extract(
        self, events: list[TrendingEvent], top_n: int = 3
    ) -> list[TrendingEvent]:
        self.calls += 1
        if self._events is not None:
            return self._events[:top_n]
        return events[:top_n]


def _passing_fit() -> IdeaFitResult:
    return IdeaFitResult(
        idea_fit=True,
        mode=ContentMode.wish,
        heat_score=0.9,
        recency_days=3.0,
        reason="Strong wish-fulfillment signal around a recognisable fictional IP.",
        kill_reason=None,
    )


class FakeIdeaFitGate:
    """Always passes (idea_fit=True) by default; set ``fit`` to override."""

    def __init__(self, fit: IdeaFitResult | None = None) -> None:
        self._fit = fit if fit is not None else _passing_fit()
        self.calls: list[TrendingEvent] = []

    def evaluate(self, event: TrendingEvent) -> IdeaFitResult:
        self.calls.append(event)
        return self._fit


class FakeGapAgent:
    def __init__(self, gap: GapAnalysis | None = None) -> None:
        self._gap = gap if gap is not None else SAMPLE_GAP
        self.calls: list[tuple[TrendingEvent, ContextBundle | None]] = []

    def analyze(
        self, event: TrendingEvent, bundle: ContextBundle | None = None
    ) -> GapAnalysis:
        self.calls.append((event, bundle))
        return self._gap


class FakeStoryPitcher:
    """Returns a fixed idea slate (slice ①: no repitch — repair is the architect's)."""

    def __init__(self, slate: IdeaPitchSlate | None = None) -> None:
        self._slate = slate if slate is not None else SAMPLE_SLATE
        self.pitch_calls: list[tuple[TrendingEvent, GapAnalysis, ContextBundle | None]] = []

    def pitch(
        self,
        event: TrendingEvent,
        gap: GapAnalysis,
        bundle: ContextBundle | None = None,
    ) -> IdeaPitchSlate:
        self.pitch_calls.append((event, gap, bundle))
        return self._slate


class FakeStoryArchitect:
    """develop() composes a script from the idea (like the real stage);
    repair() returns a marked repaired copy carrying the failure notes."""

    def __init__(self) -> None:
        self.develop_calls: list[tuple[IdeaPitch, ContextBundle | None, str]] = []
        self.repair_calls: list[tuple[StoryScript, str]] = []

    def develop(
        self,
        idea: IdeaPitch,
        event: TrendingEvent,
        gap: GapAnalysis,
        bundle: ContextBundle | None = None,
        cast_voices: str = "",
    ) -> StoryScript:
        self.develop_calls.append((idea, bundle, cast_voices))
        return _script_for(idea)

    def repair(
        self,
        idea: IdeaPitch,
        event: TrendingEvent,
        gap: GapAnalysis,
        failed_script: StoryScript,
        failure_notes: str,
        bundle: ContextBundle | None = None,
        cast_voices: str = "",
    ) -> StoryScript:
        self.repair_calls.append((failed_script, failure_notes))
        return failed_script.model_copy(
            update={"logline": f"[repaired] {failed_script.logline}"}
        )


class FakeStoryCraftGate:
    """Returns pass/fail per a predicate on the script (default: everything passes)."""

    def __init__(self, pass_predicate=None) -> None:
        self._pass = pass_predicate or (lambda script: True)
        self.calls: list[StoryScript] = []

    def evaluate(
        self, script: StoryScript, event: TrendingEvent, gap: GapAnalysis
    ) -> StoryCraftVerdict:
        self.calls.append(script)
        return _passing_verdict() if self._pass(script) else _failing_verdict()


class FakeContextAgent:
    """Returns a fixed (event, bundle, web_text) triple; records the topic."""

    def __init__(
        self,
        event: TrendingEvent | None = None,
        bundle: ContextBundle | None = None,
        web_text: str = "raw web research text about the topic",
    ) -> None:
        self._event = event if event is not None else SAMPLE_TOPIC_EVENT
        self._bundle = bundle if bundle is not None else SAMPLE_BUNDLE
        self._web_text = web_text
        self.calls: list[str] = []
        self.max_run_apify_cost = 2.00

    def gather(self, topic: str) -> tuple[TrendingEvent, ContextBundle, str]:
        self.calls.append(topic)
        return self._event, self._bundle, self._web_text


class FakeGroundingChecker:
    """coheres per a predicate on the script (default: everything coheres)."""

    def __init__(self, cohere_predicate=None) -> None:
        self._coheres = cohere_predicate or (lambda script: True)
        self.calls: list[StoryScript] = []

    def check(self, script, topic, embedder, session, k: int = 3) -> GroundingVerdict:
        self.calls.append(script)
        if self._coheres(script):
            return GroundingVerdict(reasoning="coheres", conflicts=[])
        return GroundingVerdict(
            reasoning="clash",
            conflicts=["canon: they are siblings; pitch: they are lovers"],
        )


class _RecordingIndex:
    """Stand-in for fridge.index_web_text (sqlite can't run pgvector). Records
    each call's (topic, web_text) and reports a chunk count."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, topic, web_text, embedder, session) -> int:
        self.calls.append((topic, web_text))
        return 1


_SENTINEL_EMBEDDER = object()  # only reaches the (faked) index + checker


def pick_first() -> str:
    """Simulated user selection: idea [1] on the slate."""
    return "1"


def test_approved_path(db, tmp_path):
    pitcher = FakeStoryPitcher()
    architect = FakeStoryArchitect()
    gate = FakeStoryCraftGate()  # the developed script passes

    run_pitch_pipeline(
        db,
        FakeScraper(),
        FakeExtractor(),
        FakeIdeaFitGate(),
        FakeGapAgent(),
        pitcher,
        architect,
        gate,
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    # Only the PICKED idea was developed and judged.
    assert len(architect.develop_calls) == 1
    assert architect.develop_calls[0][0] is SAMPLE_SLATE.ideas[0]
    assert len(gate.calls) == 1

    approved = db.query(AnglePitchRecord).filter_by(approved=True).all()
    assert len(approved) == 1
    assert approved[0].take == SAMPLE_SLATE.ideas[0].logline
    assert approved[0].killed_by_gate is False
    assert approved[0].mode == "wish"
    assert approved[0].idea_json is not None
    assert approved[0].story_json is not None
    assert approved[0].craft_verdict_json is not None
    # Credits priced off the developed script's beats (3 * 3s * 4.5).
    assert approved[0].estimated_cost_credits == pytest.approx(40.5)

    # The unpicked idea persisted as idea-only: no script, no verdict, 0 cr.
    unpicked = db.query(AnglePitchRecord).filter_by(approved=None).one()
    assert unpicked.idea_json is not None
    assert unpicked.story_json is None
    assert unpicked.craft_verdict_json is None
    assert unpicked.estimated_cost_credits == 0.0

    event = db.query(TrendingEventRecord).filter_by(
        id=approved[0].trending_event_id
    ).one()
    assert event.selected_for_pitching is True
    assert event.context_bundle is None  # Path A -> no bundle

    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1
    data = json.loads(json_files[0].read_text())
    assert data["pitch_id"] == approved[0].id
    assert data["mode"] == "wish"
    assert data["logline"] == SAMPLE_SLATE.ideas[0].logline
    # The handoff carries the developed SCRIPT (beats present).
    assert isinstance(data["story"], dict)
    assert len(data["story"]["beats"]) == 3
    assert data["trendiness_score"] == pytest.approx(0.92)


def test_dry_run_writes_nothing_and_never_develops(db, tmp_path):
    architect = FakeStoryArchitect()
    gate = FakeStoryCraftGate()

    run_pitch_pipeline(
        db,
        FakeScraper(),
        FakeExtractor(),
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(),
        architect,
        gate,
        dry_run=True,
        choice_provider=None,
        output_dir=tmp_path,
    )

    assert db.query(TrendingEventRecord).count() == 0
    assert db.query(AnglePitchRecord).count() == 0
    assert len(list(tmp_path.glob("*.json"))) == 0
    # Dry run stops at the idea slate — no paid development, no judging.
    assert architect.develop_calls == []
    assert gate.calls == []


def test_failing_script_repaired_then_passes(db, tmp_path):
    """Gate fails the developed script -> ONE architect repair with the failure
    notes -> passes -> approved."""
    architect = FakeStoryArchitect()
    gate = FakeStoryCraftGate(pass_predicate=lambda s: "[repaired]" in s.logline)

    run_pitch_pipeline(
        db,
        FakeScraper(),
        FakeExtractor(),
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(),
        architect,
        gate,
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    # Exactly one repair, carrying the gate's failure notes.
    assert len(architect.repair_calls) == 1
    assert architect.repair_calls[0][1] == "beat 2 needs a real turn"
    approved = db.query(AnglePitchRecord).filter_by(approved=True).one()
    assert "[repaired]" in approved.story_json["logline"]
    assert approved.killed_by_gate is False


def test_script_failing_twice_is_killed(db, tmp_path):
    """Gate fails even after the one repair -> chosen record persisted
    killed_by_gate=True with its verdict; nothing approved, no handoff."""
    architect = FakeStoryArchitect()
    gate = FakeStoryCraftGate(pass_predicate=lambda s: False)  # never passes

    result = run_pitch_pipeline(
        db,
        FakeScraper(),
        FakeExtractor(),
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(),
        architect,
        gate,
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    assert result is None  # nothing approved
    assert len(architect.repair_calls) == 1  # bounded: exactly one repair
    killed = db.query(AnglePitchRecord).filter_by(killed_by_gate=True).all()
    assert len(killed) == 1
    assert killed[0].story_json is not None
    assert killed[0].craft_verdict_json is not None
    assert db.query(AnglePitchRecord).filter_by(approved=True).count() == 0
    assert len(list(tmp_path.glob("*.json"))) == 0  # no handoff written


def test_topic_branch_skips_scraper_and_threads_bundle(db, tmp_path):
    """Path B: --topic -> scraper+extractor NOT called; context_agent.gather runs;
    gap, pitcher AND architect receive the bundle; context_bundle column populated."""
    scraper = FakeScraper()
    extractor = FakeExtractor()
    gap_agent = FakeGapAgent()
    pitcher = FakeStoryPitcher()
    architect = FakeStoryArchitect()
    context_agent = FakeContextAgent()

    run_pitch_pipeline(
        db,
        scraper,
        extractor,
        FakeIdeaFitGate(),
        gap_agent,
        pitcher,
        architect,
        FakeStoryCraftGate(),
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
        context_agent=context_agent,
        topic="Wuthering Waves Jinhsi",
    )

    assert scraper.calls == 0, "scraper.fetch must not run in Path B"
    assert extractor.calls == 0, "extractor.extract must not run in Path B"
    assert context_agent.calls == ["Wuthering Waves Jinhsi"]

    # Gap, pitcher, and the architect all received the bundle.
    assert gap_agent.calls[0][1] is SAMPLE_BUNDLE, "gap must receive the bundle"
    assert len(pitcher.pitch_calls) == 1
    assert pitcher.pitch_calls[0][2] is SAMPLE_BUNDLE, "pitcher must receive the bundle"
    assert architect.develop_calls[0][1] is SAMPLE_BUNDLE, "architect must receive the bundle"

    # Persisted event row carries the serialized bundle.
    event_row = db.query(TrendingEventRecord).one()
    assert event_row.context_bundle is not None
    assert event_row.context_bundle["summary"] == SAMPLE_BUNDLE.summary

    approved = db.query(AnglePitchRecord).filter_by(approved=True).all()
    assert len(approved) == 1


def _killing_fit() -> IdeaFitResult:
    return IdeaFitResult(
        idea_fit=False,
        mode=ContentMode.other,
        heat_score=0.2,
        recency_days=1.0,
        reason="Subject is a real athlete, not a recognisable fictional character.",
        kill_reason="not_fictional: subject is not a recognisable fictional character/IP",
    )


def test_force_overrides_gate_kill_but_not_craft_gate(db, tmp_path):
    """--force: a gate-killed event proceeds to gap/pitch anyway (advisory gate),
    but the craft gate still applies — force is not a quality bypass."""
    gap_agent = FakeGapAgent()
    pitcher = FakeStoryPitcher()

    run_pitch_pipeline(
        db,
        None,
        None,
        FakeIdeaFitGate(fit=_killing_fit()),
        gap_agent,
        pitcher,
        FakeStoryArchitect(),
        FakeStoryCraftGate(),  # craft gate passes everything here
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
        context_agent=FakeContextAgent(),
        topic="Wuthering Waves Jinhsi",
        force=True,
    )

    # The gate said kill, but gap/pitch ran and an approval landed.
    assert len(gap_agent.calls) == 1
    assert len(pitcher.pitch_calls) == 1
    assert db.query(AnglePitchRecord).filter_by(approved=True).count() == 1


def test_gate_kill_still_kills_without_force(db, tmp_path):
    """Same killing gate, force absent -> pipeline stops at the gate."""
    gap_agent = FakeGapAgent()

    result = run_pitch_pipeline(
        db,
        None,
        None,
        FakeIdeaFitGate(fit=_killing_fit()),
        gap_agent,
        FakeStoryPitcher(),
        FakeStoryArchitect(),
        FakeStoryCraftGate(),
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
        context_agent=FakeContextAgent(),
        topic="Wuthering Waves Jinhsi",
    )

    assert result is None
    assert len(gap_agent.calls) == 0
    assert db.query(AnglePitchRecord).count() == 0


def test_unresolved_facts_flags_and_persists_without_running_gap_or_pitch(db, tmp_path):
    """A bundle with non-empty unresolved_facts is flagged: persisted as its own
    TrendingEventRecord row (so a human can review it later), but gap_agent/
    story_pitcher/architect/craft gate never run for it — unlike a plain
    idea-fit-gate kill, which persists nothing."""
    idea_fit_gate = FakeIdeaFitGate()
    gap_agent = FakeGapAgent()
    pitcher = FakeStoryPitcher()
    architect = FakeStoryArchitect()
    craft_gate = FakeStoryCraftGate()
    context_agent = FakeContextAgent(event=SAMPLE_TOPIC_EVENT, bundle=FLAGGED_BUNDLE)

    result = run_pitch_pipeline(
        db,
        None,
        None,
        idea_fit_gate,
        gap_agent,
        pitcher,
        architect,
        craft_gate,
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
        context_agent=context_agent,
        topic="Wistoria fans imagining what if Elfie won Will",
    )

    assert result is None
    assert len(idea_fit_gate.calls) == 0
    assert len(gap_agent.calls) == 0
    assert len(pitcher.pitch_calls) == 0
    assert architect.develop_calls == []
    assert len(craft_gate.calls) == 0

    row = db.query(TrendingEventRecord).one()
    assert row.headline == SAMPLE_TOPIC_EVENT.headline
    assert row.unresolved_facts == FLAGGED_BUNDLE.unresolved_facts
    assert row.dominant_emotion is None
    assert row.audience_want is None
    assert db.query(AnglePitchRecord).count() == 0


def test_single_event_bundle_proceeds_even_when_unresolved(db, tmp_path):
    """A pre-built bundle (e.g. loaded from a stored TrendingEventRecord by
    scripts/repitch_event.py, not gathered live via topic/context_agent) is
    NOT subject to the flag-and-skip check — repitch_event.py already prints
    unresolved_facts for human review before calling run_pitch_pipeline."""
    idea_fit_gate = FakeIdeaFitGate()
    gap_agent = FakeGapAgent()
    pitcher = FakeStoryPitcher()
    architect = FakeStoryArchitect()
    craft_gate = FakeStoryCraftGate()

    result = run_pitch_pipeline(
        db,
        FakeScraper(events=[SAMPLE_TOPIC_EVENT]),
        FakeExtractor(),
        idea_fit_gate,
        gap_agent,
        pitcher,
        architect,
        craft_gate,
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
        single_event_bundle=FLAGGED_BUNDLE,
    )

    assert result is not None
    assert len(idea_fit_gate.calls) == 1
    assert len(gap_agent.calls) == 1
    assert gap_agent.calls[0][1] is FLAGGED_BUNDLE, "gap must receive the bundle"
    assert len(pitcher.pitch_calls) == 1
    assert pitcher.pitch_calls[0][2] is FLAGGED_BUNDLE, "pitcher must receive the bundle"
    assert architect.develop_calls[0][1] is FLAGGED_BUNDLE, "architect must receive the bundle"
    assert len(craft_gate.calls) == 1  # only the picked idea's script is judged

    row = db.query(TrendingEventRecord).one()
    assert row.headline == SAMPLE_TOPIC_EVENT.headline
    # unresolved_facts is only ever written by the flag-and-skip branch; the
    # normal persist path this event now takes never sets it.
    assert row.unresolved_facts is None
    # But the flag isn't lost — the whole bundle (including unresolved_facts)
    # is still serialized into context_bundle, same as any other bundled event.
    assert row.context_bundle is not None
    assert row.context_bundle["unresolved_facts"] == FLAGGED_BUNDLE.unresolved_facts

    approved = db.query(AnglePitchRecord).filter_by(approved=True).all()
    assert len(approved) == 1


def test_unresolved_facts_not_persisted_in_dry_run(db, tmp_path):
    context_agent = FakeContextAgent(event=SAMPLE_TOPIC_EVENT, bundle=FLAGGED_BUNDLE)

    run_pitch_pipeline(
        db,
        None,
        None,
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(),
        FakeStoryArchitect(),
        FakeStoryCraftGate(),
        dry_run=True,
        choice_provider=None,
        output_dir=tmp_path,
        context_agent=context_agent,
        topic="Wistoria fans imagining what if Elfie won Will",
    )

    assert db.query(TrendingEventRecord).count() == 0


def test_topic_branch_without_context_agent_raises(db, tmp_path):
    """topic set but context_agent=None -> ValueError, not a silent scraper run."""
    with pytest.raises(ValueError, match="context_agent"):
        run_pitch_pipeline(
            db,
            FakeScraper(),
            FakeExtractor(),
            FakeIdeaFitGate(),
            FakeGapAgent(),
            FakeStoryPitcher(),
            FakeStoryArchitect(),
            FakeStoryCraftGate(),
            dry_run=True,
            choice_provider=None,
            output_dir=tmp_path,
            context_agent=None,
            topic="some topic",
        )


# ---------------------------------------------------------------------------
# Grounding check wiring (Task 1.5) — Path B only, index on gather, one repair.
# Slice ①: grounding judges the developed SCRIPT (that's where story facts
# now materialize), so it runs once, on the picked idea's script.
# ---------------------------------------------------------------------------


def test_grounding_pass_indexes_and_persists_verdict(db, tmp_path, monkeypatch):
    """Path B with fridge machinery: raw web text is indexed on gather, the
    developed script is grounding-checked, and a cohering verdict is persisted."""
    recorder = _RecordingIndex()
    monkeypatch.setattr(pitch_angles_module, "index_web_text", recorder)
    checker = FakeGroundingChecker()  # everything coheres
    context_agent = FakeContextAgent()

    run_pitch_pipeline(
        db,
        None,
        None,
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(),
        FakeStoryArchitect(),
        FakeStoryCraftGate(),
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
        context_agent=context_agent,
        topic="Wuthering Waves Jinhsi",
        embedder=_SENTINEL_EMBEDDER,
        grounding_checker=checker,
    )

    # Raw web text indexed exactly once, scoped to the run's topic.
    assert recorder.calls == [("Wuthering Waves Jinhsi", context_agent._web_text)]
    # The picked idea's developed script was grounding-checked.
    assert len(checker.calls) == 1
    assert isinstance(checker.calls[0], StoryScript)
    approved = db.query(AnglePitchRecord).filter_by(approved=True).one()
    assert approved.grounding_verdict_json is not None
    assert approved.grounding_verdict_json["coheres"] is True


def test_grounding_conflict_repaired_then_coheres(db, tmp_path, monkeypatch):
    """A script that contradicts canon gets ONE architect repair with the
    conflicts as failure notes, then coheres -> approved as the repaired copy."""
    monkeypatch.setattr(pitch_angles_module, "index_web_text", _RecordingIndex())
    architect = FakeStoryArchitect()
    checker = FakeGroundingChecker(cohere_predicate=lambda s: "[repaired]" in s.logline)

    run_pitch_pipeline(
        db,
        None,
        None,
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(),
        architect,
        FakeStoryCraftGate(),  # craft passes -> the repair is grounding-driven
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
        context_agent=FakeContextAgent(),
        topic="Wuthering Waves Jinhsi",
        embedder=_SENTINEL_EMBEDDER,
        grounding_checker=checker,
    )

    assert len(architect.repair_calls) == 1
    assert architect.repair_calls[0][1] == "canon: they are siblings; pitch: they are lovers"
    approved = db.query(AnglePitchRecord).filter_by(approved=True).one()
    assert "[repaired]" in approved.story_json["logline"]
    assert approved.grounding_verdict_json["coheres"] is True
    assert approved.killed_by_gate is False


def test_grounding_conflict_survives_repair_is_killed(db, tmp_path, monkeypatch):
    """A canon contradiction that survives the one repair -> script killed,
    verdict persisted with coheres=False, nothing approved."""
    monkeypatch.setattr(pitch_angles_module, "index_web_text", _RecordingIndex())
    checker = FakeGroundingChecker(cohere_predicate=lambda s: False)  # never coheres

    result = run_pitch_pipeline(
        db,
        None,
        None,
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(),
        FakeStoryArchitect(),
        FakeStoryCraftGate(),  # craft passes; grounding is what kills
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
        context_agent=FakeContextAgent(),
        topic="Wuthering Waves Jinhsi",
        embedder=_SENTINEL_EMBEDDER,
        grounding_checker=checker,
    )

    assert result is None
    killed = db.query(AnglePitchRecord).filter_by(killed_by_gate=True).all()
    assert len(killed) == 1
    assert killed[0].grounding_verdict_json is not None
    assert killed[0].grounding_verdict_json["coheres"] is False
    assert db.query(AnglePitchRecord).filter_by(approved=True).count() == 0


def test_floor_rechecked_after_grounding_repair(db, tmp_path, monkeypatch):
    """Regression (code review, Critical): a grounding repair that rewrites the
    script and DROPS the profiled speaker's line must be killed by the dialogue
    floor — even though grounding itself now coheres."""
    monkeypatch.setattr(pitch_angles_module, "index_web_text", _RecordingIndex())
    # Jinhsi (slug "jinhsi") is the sole profiled cast member.
    monkeypatch.setattr(
        "src.monitor.voice_profiles.load_cast_profiles",
        lambda *a, **k: {"jinhsi": "## Fingerprint\nregal"},
    )

    jinhsi_idea = _idea(
        "jinhsi one",
        characters=[CharacterRef(name="Jinhsi", ip_source="Wuthering Waves")],
    )
    slate = IdeaPitchSlate(ideas=[jinhsi_idea, _idea("jinhsi two")])

    def _spoken_beats() -> list[StoryBeat]:
        cast = ["Jinhsi"]
        return [
            StoryBeat(role=BeatRole.establish, visual_line="v", narration_line=None,
                      shot_size=ShotSize.wide, characters_in_frame=cast),
            StoryBeat(role=BeatRole.build, visual_line="v", narration_line=None,
                      shot_size=ShotSize.medium, characters_in_frame=cast),
            StoryBeat(role=BeatRole.payoff, visual_line="v", narration_line=None,
                      dialogue_line="It ends here.", speaker="Jinhsi",
                      shot_size=ShotSize.close_up, characters_in_frame=cast,
                      hero_moment=True),
        ]

    class _StripsDialogueOnRepair(FakeStoryArchitect):
        """develop() = profiled speaker with a line; repair() drops the line
        (simulating a grounding repair that rewrote the beats)."""

        def develop(self, idea, event, gap, bundle=None, cast_voices=""):
            self.develop_calls.append((idea, bundle, cast_voices))
            return _script_for(idea, beats=_spoken_beats())

        def repair(self, idea, event, gap, failed_script, failure_notes,
                   bundle=None, cast_voices=""):
            self.repair_calls.append((failed_script, failure_notes))
            silent_beats = [
                b.model_copy(update={"dialogue_line": None, "speaker": None})
                for b in failed_script.beats
            ]
            return failed_script.model_copy(
                update={"logline": f"[repaired] {failed_script.logline}",
                        "beats": silent_beats}
            )

    # Grounding coheres only once the script is silent — i.e. after the repair.
    checker = FakeGroundingChecker(
        cohere_predicate=lambda s: all(b.dialogue_line is None for b in s.beats)
    )

    result = run_pitch_pipeline(
        db,
        None,
        None,
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(slate=slate),
        _StripsDialogueOnRepair(),
        FakeStoryCraftGate(),  # craft passes; grounding+floor are what act
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
        context_agent=FakeContextAgent(),
        topic="Wuthering Waves Jinhsi",
        embedder=_SENTINEL_EMBEDDER,
        grounding_checker=checker,
    )

    # Nothing approved; the chosen script killed BY THE FLOOR even though
    # grounding cohered on the (silent) repaired script.
    assert result is None
    killed = db.query(AnglePitchRecord).filter_by(killed_by_gate=True).all()
    assert len(killed) == 1
    assert killed[0].grounding_verdict_json["coheres"] is True


def test_grounding_skipped_in_dry_run(db, tmp_path, monkeypatch):
    """dry_run keeps the fridge side-effect-free: no index write, no check."""
    recorder = _RecordingIndex()
    monkeypatch.setattr(pitch_angles_module, "index_web_text", recorder)
    checker = FakeGroundingChecker()

    run_pitch_pipeline(
        db,
        None,
        None,
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(),
        FakeStoryArchitect(),
        FakeStoryCraftGate(),
        dry_run=True,
        choice_provider=None,
        output_dir=tmp_path,
        context_agent=FakeContextAgent(),
        topic="Wuthering Waves Jinhsi",
        embedder=_SENTINEL_EMBEDDER,
        grounding_checker=checker,
    )

    assert recorder.calls == []
    assert checker.calls == []


def test_grounding_topic_override_grounds_without_rescrape(db, tmp_path, monkeypatch):
    """Cheap re-pitch path (repitch_event.py): single_event_bundle + grounding_topic
    with topic=None runs grounding against the fridge WITHOUT triggering a Path B
    re-scrape/index. Locks the grounding_topic decouple."""
    recorder = _RecordingIndex()
    monkeypatch.setattr(pitch_angles_module, "index_web_text", recorder)
    checker = FakeGroundingChecker()  # coheres

    run_pitch_pipeline(
        db,
        FakeScraper(events=[SAMPLE_TOPIC_EVENT]),
        FakeExtractor(),
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(),
        FakeStoryArchitect(),
        FakeStoryCraftGate(),
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
        single_event_bundle=SAMPLE_BUNDLE,
        embedder=_SENTINEL_EMBEDDER,
        grounding_checker=checker,
        grounding_topic="Wuthering Waves Jinhsi",
    )

    # topic is None -> no re-scrape index fired.
    assert recorder.calls == []
    # ...but grounding still ran on the developed script, scoped to the override.
    assert len(checker.calls) == 1
    approved = db.query(AnglePitchRecord).filter_by(approved=True).one()
    assert approved.grounding_verdict_json is not None
    assert approved.grounding_verdict_json["coheres"] is True
