import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.models.angle_pitch import AnglePitchRecord
from src.models.trending_event import TrendingEventRecord
from src.database import Base
from src.monitor.schemas import (
    AnglePitch,
    AnglePitchSlate,
    ContextBundle,
    GapAnalysis,
    IdeaFitResult,
    ContentMode,
    RenderBackend,
    RoutingDecision,
    TrendingEvent,
)
from scripts.pitch_angles import run_pitch_pipeline

# ---------------------------------------------------------------------------
# Sample pipeline data (one event → one gap → three angles)
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

SAMPLE_SLATE = AnglePitchSlate(
    angles=[
        AnglePitch(
            take="The dragon finally breathes fire over Tokyo Tower at dawn",
            format_description="Single wide aerial shot, slow push-in as flame erupts",
            render_backend=RenderBackend.visual_satire,
            estimated_cost_credits=24.0,
            gap_satisfaction_rationale="Shows the fire-breath payoff fans were denied",
            legal_flag=False,
        ),
        AnglePitch(
            take="Breaking news helicopter footage captures the dragon's fire breath",
            format_description="Mock news B-roll, shaky helicopter POV, lower-third chyron",
            render_backend=RenderBackend.commentary_voiceover,
            estimated_cost_credits=24.0,
            gap_satisfaction_rationale="Delivers the climax through a documentary news frame",
            legal_flag=False,
        ),
        AnglePitch(
            take="A-list actor watches the dragon breathe fire from a rooftop",
            format_description="Split-screen: celebrity reaction face + dragon fire wide shot",
            render_backend=RenderBackend.narrative_alt,
            estimated_cost_credits=30.0,
            gap_satisfaction_rationale="Pairs the wish-fulfillment with a recognizable reaction",
            legal_flag=True,
        ),
    ]
)

# Pick "1" in tests → first angle above (visual_satire, no substitution).
ROUTED_VISUAL = RoutingDecision(
    backend=RenderBackend.visual_satire,
    is_substitute=False,
    substitution_note="",
)

ROUTED_SUBSTITUTE = RoutingDecision(
    backend=RenderBackend.visual_satire,
    is_substitute=True,
    substitution_note="Wished-for backend 'commentary_voiceover' is not available; substituted 'visual_satire'.",
)


AVAILABLE_BACKENDS = {
    RenderBackend.visual_satire: True,
    RenderBackend.commentary_voiceover: False,
    RenderBackend.narrative_alt: False,
    RenderBackend.unknown: False,
}

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


class FakeAnglePitcher:
    def __init__(self, slate: AnglePitchSlate | None = None) -> None:
        self._slate = slate if slate is not None else SAMPLE_SLATE
        self.calls: list[tuple[TrendingEvent, GapAnalysis, ContextBundle | None]] = []

    def pitch(
        self,
        event: TrendingEvent,
        gap: GapAnalysis,
        bundle: ContextBundle | None = None,
    ) -> AnglePitchSlate:
        self.calls.append((event, gap, bundle))
        return self._slate


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


class FakeFormatRouter:
    """Returns a fixed decision per wished-for backend, or one global override."""

    def __init__(
        self,
        *,
        default: RoutingDecision | None = None,
        by_backend: dict[RenderBackend, RoutingDecision] | None = None,
    ) -> None:
        self._default = default if default is not None else ROUTED_VISUAL
        self._by_backend = by_backend or {
            RenderBackend.visual_satire: ROUTED_VISUAL,
            RenderBackend.commentary_voiceover: ROUTED_SUBSTITUTE,
            RenderBackend.narrative_alt: ROUTED_SUBSTITUTE,
            RenderBackend.unknown: ROUTED_SUBSTITUTE,
        }
        self.calls: list[AnglePitch] = []

    def route(self, angle: AnglePitch) -> RoutingDecision:
        self.calls.append(angle)
        return self._by_backend.get(angle.render_backend, self._default)


def pick_first() -> str:
    """Simulated user selection: angle [1] on a single-event slate."""
    return "1"


def test_approved_path(db, tmp_path):
    scraper = FakeScraper()
    extractor = FakeExtractor()
    idea_fit_gate = FakeIdeaFitGate()
    gap_agent = FakeGapAgent()
    angle_pitcher = FakeAnglePitcher()
    format_router = FakeFormatRouter()

    run_pitch_pipeline(
        db,
        scraper,
        extractor,
        idea_fit_gate,
        gap_agent,
        angle_pitcher,
        format_router,
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
    )

    approved_pitches = db.query(AnglePitchRecord).filter_by(approved=True).all()
    assert len(approved_pitches) == 1
    assert SAMPLE_SLATE.angles[0].take == approved_pitches[0].take

    event = db.query(TrendingEventRecord).filter_by(id=approved_pitches[0].trending_event_id).one()
    assert event.selected_for_pitching is True
    # Path A → no bundle persisted.
    assert event.context_bundle is None

    json_files = list(tmp_path.glob("*.json"))
    assert len(json_files) == 1

    data = json.loads(json_files[0].read_text())

    assert data["routed_backend"] == "visual_satire"
    assert data["trendiness_score"] == pytest.approx(0.92)
    assert data["angle_pitch_id"] == approved_pitches[0].id


def test_dry_run_writes_nothing(db, tmp_path):
    scraper = FakeScraper()
    extractor = FakeExtractor()
    idea_fit_gate = FakeIdeaFitGate()
    gap_agent = FakeGapAgent()
    angle_pitcher = FakeAnglePitcher()
    format_router = FakeFormatRouter()

    run_pitch_pipeline(
        db,
        scraper,
        extractor,
        idea_fit_gate,
        gap_agent,
        angle_pitcher,
        format_router,
        dry_run=True,
        choice_provider=None,
        output_dir=tmp_path,
    )

    assert db.query(TrendingEventRecord).count() == 0
    assert db.query(AnglePitchRecord).count() == 0
    assert len(list(tmp_path.glob("*.json"))) == 0


def test_topic_branch_skips_scraper_and_threads_bundle(db, tmp_path):
    """Path B: --topic → scraper+extractor NOT called; context_agent.gather
    runs; gap & pitcher receive the bundle; context_bundle column populated."""
    scraper = FakeScraper()
    extractor = FakeExtractor()
    idea_fit_gate = FakeIdeaFitGate()
    gap_agent = FakeGapAgent()
    angle_pitcher = FakeAnglePitcher()
    format_router = FakeFormatRouter()
    context_agent = FakeContextAgent()

    run_pitch_pipeline(
        db,
        scraper,
        extractor,
        idea_fit_gate,
        gap_agent,
        angle_pitcher,
        format_router,
        dry_run=False,
        choice_provider=pick_first,
        output_dir=tmp_path,
        context_agent=context_agent,
        topic="Wuthering Waves Jinhsi",
    )

    # Scraper/extractor skipped in Path B.
    assert scraper.calls == 0, "scraper.fetch must not run in Path B"
    assert extractor.calls == 0, "extractor.extract must not run in Path B"

    # Agent gathered the topic exactly once.
    assert context_agent.calls == ["Wuthering Waves Jinhsi"]

    # Gate evaluated the synthesized manual-origin event.
    assert len(idea_fit_gate.calls) == 1
    assert idea_fit_gate.calls[0].origin == "manual"

    # Gap & pitcher received the bundle.
    assert len(gap_agent.calls) == 1
    assert gap_agent.calls[0][1] is SAMPLE_BUNDLE, "gap must receive the bundle"
    assert len(angle_pitcher.calls) == 1  # one event → one pitch() call
    assert angle_pitcher.calls[0][2] is SAMPLE_BUNDLE, "pitcher must receive the bundle"

    # Persisted event row carries the serialized bundle.
    event_row = db.query(TrendingEventRecord).one()
    assert event_row.context_bundle is not None
    assert event_row.context_bundle["summary"] == SAMPLE_BUNDLE.summary
    assert event_row.context_bundle["key_moments"] == SAMPLE_BUNDLE.key_moments
    assert event_row.context_bundle["references"] == SAMPLE_BUNDLE.references

    # Approved pitch row exists (pick_first chose angle [1]).
    approved = db.query(AnglePitchRecord).filter_by(approved=True).all()
    assert len(approved) == 1


def test_topic_branch_without_context_agent_raises(db, tmp_path):
    """topic set but context_agent=None → ValueError, not a silent scraper run."""
    scraper = FakeScraper()
    extractor = FakeExtractor()
    idea_fit_gate = FakeIdeaFitGate()
    gap_agent = FakeGapAgent()
    angle_pitcher = FakeAnglePitcher()
    format_router = FakeFormatRouter()

    with pytest.raises(ValueError, match="context_agent"):
        run_pitch_pipeline(
            db,
            scraper,
            extractor,
            idea_fit_gate,
            gap_agent,
            angle_pitcher,
            format_router,
            dry_run=True,
            choice_provider=None,
            output_dir=tmp_path,
            context_agent=None,
            topic="some topic",
        )
