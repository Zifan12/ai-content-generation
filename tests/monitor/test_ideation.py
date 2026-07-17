"""Tests for the Ideator stage (src/monitor/ideation.py, Exilus PRD ticket 06/D7).

Mirrors tests/monitor/test_story_pitcher.py's FakeLLM idiom, but the fixtures
are TopicBrief/FactionMap (the two pinned Exilus artifacts) instead of
TrendingEvent/GapAnalysis -- this stage reads ONLY those two artifacts.
"""
import inspect
import logging

import pytest

from src.generation.story_architect import StoryArchitect
from src.monitor.ideation import Ideator, IdeationCoverageError
from src.monitor.schemas import (
    BeatRole,
    BriefField,
    Camp,
    CharacterRef,
    ContentMode,
    EvidenceQuote,
    ExilusIdea,
    ExilusSlate,
    FactionMap,
    GapAnalysis,
    IdeaPitch,
    ScriptDraft,
    ShotSize,
    StoryBeat,
    TopicBrief,
    TrendingEvent,
)
from src.rag.embedder import TextEmbedder


def _brief_field(content: str, verified: bool = True) -> BriefField:
    return BriefField(content=content, citations=["https://example.com/source"], verified=verified)


def _sample_brief() -> TopicBrief:
    return TopicBrief(
        identity=_brief_field("A shonen fantasy about a princess-knight who lost her kingdom"),
        recent_events=_brief_field("The season 3 finale aired last week, ending on a cliffhanger"),
        key_characters=_brief_field("Elfaria (protagonist), Serfort (estranged rival and friend)"),
        why_people_care=_brief_field("Fans have waited two years for a reunion arc between them"),
        open_unknowns=["whether a season 4 is confirmed"],
    )


def _camp(name: str, weight: float = 0.5) -> Camp:
    return Camp(
        name=name,
        feeling="hopeful",
        surface_want="wants Elfaria and Serfort to reunite on screen",
        deeper_desire="wants proof the years apart still mattered to both of them",
        evidence_quotes=[EvidenceQuote(quote="please just let them hug already", upvotes=120)],
        weight=weight,
    )


def _sample_faction_map(*camp_names: str) -> FactionMap:
    n = len(camp_names)
    return FactionMap(camps=[_camp(name, weight=1.0 / n) for name in camp_names])


def _idea(logline: str, target_camp: str, mode: ContentMode = ContentMode.wish) -> ExilusIdea:
    return ExilusIdea(
        logline=logline,
        mode=mode,
        characters=[CharacterRef(name="Elfaria", ip_source="Exilus")],
        desired_moment="Elfaria and Serfort finally embrace",
        why_it_lands="delivers the reunion fans have waited two years for",
        legal_flag=False,
        target_camp=target_camp,
    )


def _slate_covering(camp_names: list[str], n: int = 8) -> ExilusSlate:
    """Build a slate of ``n`` ideas, round-robin across ``camp_names`` (every camp covered)."""
    ideas = [
        _idea(logline=f"Story {i}", target_camp=camp_names[i % len(camp_names)]) for i in range(n)
    ]
    return ExilusSlate(ideas=ideas)


class FakeLLM:
    """Returns queued results in order; the last result repeats if over-called."""

    def __init__(self, results: object) -> None:
        self._results = list(results) if isinstance(results, list) else [results]
        self.calls: list[dict] = []

    def parse(self, prompt: str, response_model: type, **kwargs: object) -> object:
        self.calls.append({"prompt": prompt, "response_model": response_model, **kwargs})
        self.prompt = prompt  # last call's prompt, convenience for single-call tests
        if len(self._results) > 1:
            return self._results.pop(0)
        return self._results[0]


class FakeEmbedder(TextEmbedder):
    def __init__(self) -> None:
        self.texts: list[str] | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts = texts
        basis = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        return [basis[i % 3] for i in range(len(texts))]

    @property
    def dim(self) -> int:
        return 1024

    @property
    def model_name(self) -> str:
        return "fake-embedder"


def test_generate_returns_slate_within_bounds_and_covers_every_camp() -> None:
    """AC2/AC3: 8-15 ideas, every camp represented at least once."""
    camp_names = ["the romantics", "the satirists", "the skeptics"]
    faction_map = _sample_faction_map(*camp_names)
    llm = FakeLLM(_slate_covering(camp_names, n=10))
    ideator = Ideator(llm=llm, embedder=FakeEmbedder())

    result = ideator.generate(_sample_brief(), faction_map)

    assert 8 <= len(result.ideas) <= 15
    assert {idea.target_camp for idea in result.ideas} == set(camp_names)


def test_uneven_camp_allocation_is_accepted() -> None:
    """AC4: allocation beyond the one-per-camp floor need not be even."""
    faction_map = _sample_faction_map("camp a", "camp b")
    ideas = [_idea(f"a{i}", "camp a") for i in range(6)] + [_idea(f"b{i}", "camp b") for i in range(2)]
    llm = FakeLLM(ExilusSlate(ideas=ideas))
    ideator = Ideator(llm=llm, embedder=FakeEmbedder())

    result = ideator.generate(_sample_brief(), faction_map)

    assert len(result.ideas) == 8
    assert {idea.target_camp for idea in result.ideas} == {"camp a", "camp b"}


def test_every_idea_carries_target_camp_and_mode() -> None:
    """AC5: neither tag is ever missing (schema-enforced -- both required fields)."""
    idea = _idea("a story", "camp a")
    assert idea.target_camp == "camp a"
    assert idea.mode == ContentMode.wish


def test_exilus_idea_preserves_ideapitch_fields_unchanged() -> None:
    """AC6: ExilusIdea IS an IdeaPitch -- no downstream call site needs to change."""
    idea = _idea("a story", "camp a")
    assert isinstance(idea, IdeaPitch)
    for field in ("logline", "mode", "characters", "desired_moment", "why_it_lands", "legal_flag"):
        assert field in type(idea).model_fields


def test_reroll_passes_prior_loglines_as_do_not_repeat() -> None:
    """AC7/AC8(a): prior loglines reach the LLM call as do-not-repeat input."""
    faction_map = _sample_faction_map("camp a")
    llm = FakeLLM(_slate_covering(["camp a"], n=8))
    ideator = Ideator(llm=llm, embedder=FakeEmbedder())

    ideator.generate(_sample_brief(), faction_map, prior_loglines=("Story one", "Story two"))

    assert "<do_not_repeat>" in llm.prompt
    assert "Story one" in llm.prompt
    assert "Story two" in llm.prompt


def test_generate_signature_takes_only_brief_and_faction_map() -> None:
    """AC1/AC9: the signature itself is the proof no event/gap material can reach the call."""
    sig = inspect.signature(Ideator.generate)
    assert set(sig.parameters) - {"self"} == {"brief", "faction_map", "prior_loglines"}


def test_coverage_gap_is_retried_and_resolved() -> None:
    """D7: one bounded retry, the coverage gap named in the retry prompt."""
    faction_map = _sample_faction_map("camp a", "camp b")
    first_slate = _slate_covering(["camp a"], n=8)  # misses camp b
    second_slate = _slate_covering(["camp a", "camp b"], n=8)
    llm = FakeLLM([first_slate, second_slate])
    ideator = Ideator(llm=llm, embedder=FakeEmbedder())

    result = ideator.generate(_sample_brief(), faction_map)

    assert len(llm.calls) == 2
    assert "COVERAGE GAP" in llm.calls[1]["prompt"]
    assert "camp b" in llm.calls[1]["prompt"]
    assert {idea.target_camp for idea in result.ideas} == {"camp a", "camp b"}


def test_coverage_gap_persisting_after_retry_raises() -> None:
    """D7: exactly one retry, then raise -- never an unbounded loop."""
    faction_map = _sample_faction_map("camp a", "camp b")
    still_missing = _slate_covering(["camp a"], n=8)  # never covers camp b
    llm = FakeLLM([still_missing, still_missing])
    ideator = Ideator(llm=llm, embedder=FakeEmbedder())

    with pytest.raises(IdeationCoverageError):
        ideator.generate(_sample_brief(), faction_map)

    assert len(llm.calls) == 2  # first pass + exactly one retry


def test_diversity_check_runs_on_wide_slate_without_raising(caplog) -> None:
    """AC10: the non-gating diversity check runs over 8-15 ideas without raising/blocking."""
    faction_map = _sample_faction_map("camp a")
    llm = FakeLLM(_slate_covering(["camp a"], n=15))
    embedder = FakeEmbedder()
    ideator = Ideator(llm=llm, embedder=embedder)

    with caplog.at_level(logging.WARNING):
        result = ideator.generate(_sample_brief(), faction_map)

    assert len(result.ideas) == 15
    assert embedder.texts is not None and len(embedder.texts) == 15


def test_picked_exilus_idea_hands_off_to_story_architect_unchanged() -> None:
    """PRD Testing Decisions: pick hands off in the existing pick-level contract.

    An ExilusIdea (the Exilus lane's "pick") is fed into StoryArchitect.develop
    -- the existing D1 call shape -- with zero modification to story_architect.py.
    """
    idea = _idea("Elfaria and Serfort reunite", "camp a")
    manual_event = TrendingEvent(
        headline="Exilus manual topic run",
        subreddit="",
        url="",
        reaction_sample="",
        trendiness_score=0.0,
        virality_window_hours=0.0,
        raw_source_data={},
        origin="manual",
    )
    gap = GapAnalysis(dominant_emotion="hopeful", audience_want="the reunion", reasoning="")
    draft = ScriptDraft(
        scene_setting="a quiet courtyard at dusk",
        beats=[
            StoryBeat(
                role=BeatRole.hook,
                visual_line="Elfaria stands at the gate",
                narration_line=None,
                shot_size=ShotSize.wide,
                characters_in_frame=["Elfaria"],
                hero_moment=False,
            ),
            StoryBeat(
                role=BeatRole.turn,
                visual_line="Serfort steps into view",
                narration_line=None,
                shot_size=ShotSize.medium,
                characters_in_frame=["Elfaria"],
                hero_moment=False,
            ),
            StoryBeat(
                role=BeatRole.payoff,
                visual_line="they embrace",
                narration_line=None,
                shot_size=ShotSize.close_up,
                characters_in_frame=["Elfaria"],
                hero_moment=True,
            ),
        ],
    )
    llm = FakeLLM(draft)
    architect = StoryArchitect(llm=llm)

    script = architect.develop(idea, manual_event, gap)

    assert script.logline == idea.logline
    assert script.mode == idea.mode
    assert script.why_it_lands == idea.why_it_lands
    assert script.legal_flag == idea.legal_flag
