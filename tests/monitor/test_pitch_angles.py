import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from scripts.pitch_angles import run_pitch_pipeline
from src.database import Base
from src.models.angle_pitch import AnglePitchRecord
from src.models.trending_event import TrendingEventRecord
from src.monitor.schemas import (
    BeatRole,
    CaptionPolicy,
    CharacterRef,
    ContentMode,
    ContextBundle,
    GapAnalysis,
    IdeaFitResult,
    ShotSize,
    StoryBeat,
    StoryCraftVerdict,
    StoryPitch,
    StoryPitchSlate,
    TrendingEvent,
)

# ---------------------------------------------------------------------------
# Sample pipeline data (one event -> one gap -> a slate of story pitches)
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
    virality_window_hours=18.0,
    reasoning="The crowd was teased a payoff the footage never delivered.",
)


def _story_pitch(
    logline: str,
    *,
    mode: ContentMode = ContentMode.wish,
    legal_flag: bool = False,
) -> StoryPitch:
    """Build a schema-valid StoryPitch (3 beats, varied framing, one hero)."""
    return StoryPitch(
        logline=logline,
        mode=mode,
        characters=[CharacterRef(name="Dragon", ip_source="Original")],
        desired_moment="the dragon breathes fire over the tower",
        beats=[
            StoryBeat(
                role=BeatRole.hook,
                visual_line="wide aerial of the tower at dawn",
                narration_line=None,
                shot_size=ShotSize.establishing,
                characters_in_frame=["Dragon"],
                hero_moment=False,
            ),
            StoryBeat(
                role=BeatRole.build,
                visual_line="the dragon inhales, scales glowing",
                narration_line=None,
                shot_size=ShotSize.medium,
                characters_in_frame=["Dragon"],
                hero_moment=False,
            ),
            StoryBeat(
                role=BeatRole.payoff,
                visual_line="fire erupts over the tower",
                narration_line=None,
                shot_size=ShotSize.close_up,
                characters_in_frame=["Dragon"],
                hero_moment=True,
            ),
        ],
        caption_policy=CaptionPolicy.hook_only,
        hook_line="The fire they never showed you.",
        why_it_lands="Delivers the fire-breath payoff fans were denied.",
        legal_flag=legal_flag,
    )


SAMPLE_SLATE = StoryPitchSlate(
    pitches=[
        _story_pitch("The dragon finally breathes fire over Tokyo Tower at dawn"),
        _story_pitch("A rooftop crowd watches the dragon's fire erupt", legal_flag=True),
    ]
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
    """Returns a fixed slate; repitch returns a marked repaired copy."""

    def __init__(self, slate: StoryPitchSlate | None = None) -> None:
        self._slate = slate if slate is not None else SAMPLE_SLATE
        self.pitch_calls: list[tuple[TrendingEvent, GapAnalysis, ContextBundle | None]] = []
        self.repitch_calls: list[tuple[StoryPitch, str]] = []

    def pitch(
        self,
        event: TrendingEvent,
        gap: GapAnalysis,
        bundle: ContextBundle | None = None,
    ) -> StoryPitchSlate:
        self.pitch_calls.append((event, gap, bundle))
        return self._slate

    def repitch(
        self,
        event: TrendingEvent,
        gap: GapAnalysis,
        failed_pitch: StoryPitch,
        failure_notes: str,
        bundle: ContextBundle | None = None,
    ) -> StoryPitch:
        self.repitch_calls.append((failed_pitch, failure_notes))
        return failed_pitch.model_copy(
            update={"logline": f"[repaired] {failed_pitch.logline}"}
        )


class FakeStoryCraftGate:
    """Returns pass/fail per a predicate on the pitch (default: everything passes)."""

    def __init__(self, pass_predicate=None) -> None:
        self._pass = pass_predicate or (lambda pitch: True)
        self.calls: list[StoryPitch] = []

    def evaluate(
        self, pitch: StoryPitch, event: TrendingEvent, gap: GapAnalysis
    ) -> StoryCraftVerdict:
        self.calls.append(pitch)
        return _passing_verdict() if self._pass(pitch) else _failing_verdict()


class FakeContextAgent:
    """Returns a fixed (event, bundle) pair; records the topic."""

    def __init__(
        self,
        event: TrendingEvent | None = None,
        bundle: ContextBundle | None = None,
    ) -> None:
        self._event = event if event is not None else SAMPLE_TOPIC_EVENT
        self._bundle = bundle if bundle is not None else SAMPLE_BUNDLE
        self.calls: list[str] = []
        self.max_run_apify_cost = 2.00

    def gather(self, topic: str) -> tuple[TrendingEvent, ContextBundle]:
        self.calls.append(topic)
        return self._event, self._bundle


def pick_first() -> str:
    """Simulated user selection: pitch [1] on the surviving slate."""
    return "1"


def test_approved_path(db, tmp_path):
    pitcher = FakeStoryPitcher()
    gate = FakeStoryCraftGate()  # all pitches pass

    run_pitch_pipeline(
        db,
        FakeScraper(),
        FakeExtractor(),
        FakeIdeaFitGate(),
        FakeGapAgent(),
        pitcher,
        gate,
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    approved = db.query(AnglePitchRecord).filter_by(approved=True).all()
    assert len(approved) == 1
    assert approved[0].take == SAMPLE_SLATE.pitches[0].logline
    assert approved[0].killed_by_gate is False
    assert approved[0].mode == "wish"
    assert approved[0].story_json is not None
    assert approved[0].craft_verdict_json is not None

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
    assert data["logline"] == SAMPLE_SLATE.pitches[0].logline
    assert isinstance(data["story"], dict)
    assert data["trendiness_score"] == pytest.approx(0.92)


def test_dry_run_writes_nothing(db, tmp_path):
    run_pitch_pipeline(
        db,
        FakeScraper(),
        FakeExtractor(),
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(),
        FakeStoryCraftGate(),
        dry_run=True,
        choice_provider=None,
        output_dir=tmp_path,
    )

    assert db.query(TrendingEventRecord).count() == 0
    assert db.query(AnglePitchRecord).count() == 0
    assert len(list(tmp_path.glob("*.json"))) == 0


def test_failing_pitch_repitched_then_passes(db, tmp_path):
    """Gate fails a pitch -> repitch once with the failure notes -> passes -> slate."""
    pitcher = FakeStoryPitcher()
    gate = FakeStoryCraftGate(pass_predicate=lambda p: "[repaired]" in p.logline)

    run_pitch_pipeline(
        db,
        FakeScraper(),
        FakeExtractor(),
        FakeIdeaFitGate(),
        FakeGapAgent(),
        pitcher,
        gate,
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    # Each original pitch failed once and was repitched exactly once.
    assert len(pitcher.repitch_calls) == len(SAMPLE_SLATE.pitches)
    # The repitch received the gate's failure notes.
    assert pitcher.repitch_calls[0][1] == "beat 2 needs a real turn"
    # The approved survivor is a repaired pitch, not killed.
    approved = db.query(AnglePitchRecord).filter_by(approved=True).one()
    assert "[repaired]" in approved.take
    assert approved.killed_by_gate is False


def test_pitch_failing_twice_is_killed(db, tmp_path):
    """Gate fails even after repair -> pitch dropped, persisted killed_by_gate=True."""
    pitcher = FakeStoryPitcher()
    gate = FakeStoryCraftGate(pass_predicate=lambda p: False)  # never passes

    result = run_pitch_pipeline(
        db,
        FakeScraper(),
        FakeExtractor(),
        FakeIdeaFitGate(),
        FakeGapAgent(),
        pitcher,
        gate,
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    assert result is None  # wave died — nothing approved
    pitches = db.query(AnglePitchRecord).all()
    assert len(pitches) == len(SAMPLE_SLATE.pitches)
    assert all(p.killed_by_gate for p in pitches)
    assert all(p.craft_verdict_json is not None for p in pitches)
    assert db.query(AnglePitchRecord).filter_by(approved=True).count() == 0
    assert len(list(tmp_path.glob("*.json"))) == 0  # no handoff written


def test_topic_branch_skips_scraper_and_threads_bundle(db, tmp_path):
    """Path B: --topic -> scraper+extractor NOT called; context_agent.gather runs;
    gap & pitcher receive the bundle; context_bundle column populated."""
    scraper = FakeScraper()
    extractor = FakeExtractor()
    gap_agent = FakeGapAgent()
    pitcher = FakeStoryPitcher()
    context_agent = FakeContextAgent()

    run_pitch_pipeline(
        db,
        scraper,
        extractor,
        FakeIdeaFitGate(),
        gap_agent,
        pitcher,
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

    # Gap & pitcher received the bundle.
    assert gap_agent.calls[0][1] is SAMPLE_BUNDLE, "gap must receive the bundle"
    assert len(pitcher.pitch_calls) == 1
    assert pitcher.pitch_calls[0][2] is SAMPLE_BUNDLE, "pitcher must receive the bundle"

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
    story_pitcher/story_craft_gate never run for it — unlike a plain idea-fit-gate
    kill, which persists nothing."""
    idea_fit_gate = FakeIdeaFitGate()
    gap_agent = FakeGapAgent()
    pitcher = FakeStoryPitcher()
    craft_gate = FakeStoryCraftGate()
    context_agent = FakeContextAgent(event=SAMPLE_TOPIC_EVENT, bundle=FLAGGED_BUNDLE)

    result = run_pitch_pipeline(
        db,
        None,
        None,
        idea_fit_gate,
        gap_agent,
        pitcher,
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
    assert len(craft_gate.calls) == 0

    row = db.query(TrendingEventRecord).one()
    assert row.headline == SAMPLE_TOPIC_EVENT.headline
    assert row.unresolved_facts == FLAGGED_BUNDLE.unresolved_facts
    assert row.dominant_emotion is None
    assert row.audience_want is None
    assert db.query(AnglePitchRecord).count() == 0


def test_unresolved_facts_not_persisted_in_dry_run(db, tmp_path):
    context_agent = FakeContextAgent(event=SAMPLE_TOPIC_EVENT, bundle=FLAGGED_BUNDLE)

    run_pitch_pipeline(
        db,
        None,
        None,
        FakeIdeaFitGate(),
        FakeGapAgent(),
        FakeStoryPitcher(),
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
            FakeStoryCraftGate(),
            dry_run=True,
            choice_provider=None,
            output_dir=tmp_path,
            context_agent=None,
            topic="some topic",
        )
