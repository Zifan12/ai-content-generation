"""Tests for the pitch-grounding coherence check (Task 1.4).

Exercises the fixed 2-call RAG pipeline end-to-end with a fake LLM (dispatching
on response_model, mirroring test_gap_agent) over the REAL fridge + DB (indexing
canon chunks, mirroring test_fridge). Covers the two verdict paths and the
load-bearing empty-fridge short-circuit — the contradiction-only rule's "absence
is not a conflict" behavior.
"""

import hashlib

import numpy as np
import pytest
from sqlalchemy.orm import Session

from src.database import engine
from src.monitor.fridge import index_web_text
from src.monitor.pitch_grounding import (
    CanonQueries,
    GroundingVerdict,
    PitchGroundingChecker,
)
from src.monitor.schemas import (
    BeatRole,
    CaptionPolicy,
    CharacterRef,
    ContentMode,
    ShotSize,
    StoryBeat,
    StoryPitch,
)


class _FakeEmbedder:
    """Deterministic seeded embedder (no torch); same text -> same 1024-vec, so a
    query identical to an indexed chunk retrieves it exactly. Copied from
    test_fridge — the fridge only duck-types the embedder."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "little")
            vectors.append(np.random.default_rng(seed).standard_normal(1024).tolist())
        return vectors

    @property
    def model_name(self) -> str:
        return "fake-embedder"


class _FakeLLM:
    """Two-call fake: returns the preset CanonQueries for call-1 (response_model
    is CanonQueries) and the preset GroundingVerdict for call-2 (anything else).

    Records how many times each call fired so a test can assert call-2 was
    SKIPPED on the empty-fridge short-circuit.
    """

    def __init__(self, queries: CanonQueries, verdict: GroundingVerdict) -> None:
        self._queries = queries
        self._verdict = verdict
        self.queries_calls = 0
        self.verdict_calls = 0
        self.verdict_prompt: str | None = None

    def parse(self, prompt: str, response_model: type, **kwargs):
        if response_model is CanonQueries:
            self.queries_calls += 1
            return self._queries
        self.verdict_calls += 1
        self.verdict_prompt = prompt
        return self._verdict


# A canon chunk whose exact text is reused as the call-1 query, so the fake
# embedder self-retrieves it (cosine distance 0) and call-2 sees non-empty canon.
_CANON_CHUNK = "Rin and Len are twin siblings in the source, not a romantic couple."


def _sample_pitch() -> StoryPitch:
    """A minimal valid StoryPitch (caption_policy=none avoids the hook_line rule;
    two shot sizes satisfy the framing-variety validator)."""
    return StoryPitch(
        logline="Rin and Len finally share the balcony kiss fans were denied.",
        mode=ContentMode.wish,
        characters=[
            CharacterRef(name="Rin", ip_source="Vocaloid"),
            CharacterRef(name="Len", ip_source="Vocaloid"),
        ],
        desired_moment="the long-teased balcony kiss",
        scene_setting="a moonlit balcony at night",
        beats=[
            StoryBeat(
                role=BeatRole.hook,
                visual_line="Rin steps onto the moonlit balcony, breath held.",
                narration_line=None,
                shot_size=ShotSize.wide,
                characters_in_frame=["Rin"],
            ),
            StoryBeat(
                role=BeatRole.turn,
                visual_line="Len takes her hand at the railing.",
                narration_line=None,
                shot_size=ShotSize.medium,
                characters_in_frame=["Rin", "Len"],
            ),
            StoryBeat(
                role=BeatRole.payoff,
                visual_line="They kiss as the moon crests behind them.",
                narration_line=None,
                shot_size=ShotSize.close_up,
                characters_in_frame=["Rin", "Len"],
                hero_moment=True,
            ),
        ],
        caption_policy=CaptionPolicy.none,
        hook_line=None,
        why_it_lands="Fans mourned the couple that never was.",
        legal_flag=False,
    )


@pytest.fixture
def db():
    """Transactional session rolled back after each test (mirrors test_fridge)."""
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    trans.rollback()
    connection.close()


def test_contradiction_fails(db):
    """Canon retrieved + call-2 finds a contradiction -> coheres False, conflicts
    surfaced, and call-2 actually ran against the retrieved canon."""
    emb = _FakeEmbedder()
    assert index_web_text("topic-rin", _CANON_CHUNK, emb, db) == 1

    llm = _FakeLLM(
        queries=CanonQueries(queries=[_CANON_CHUNK]),
        verdict=GroundingVerdict(
            reasoning="Canon says twin siblings; the pitch makes them lovers.",
            conflicts=["Canon: Rin and Len are siblings; pitch: they are lovers."],
        ),
    )
    checker = PitchGroundingChecker(llm=llm)

    verdict = checker.check(_sample_pitch(), "topic-rin", emb, db)

    assert verdict.coheres is False
    assert verdict.conflicts
    assert llm.verdict_calls == 1
    # call-2 saw the retrieved canon
    assert _CANON_CHUNK in llm.verdict_prompt


def test_coheres_passes(db):
    """Canon retrieved + call-2 finds no contradiction -> coheres True, no
    conflicts."""
    emb = _FakeEmbedder()
    index_web_text("topic-rin", _CANON_CHUNK, emb, db)

    llm = _FakeLLM(
        queries=CanonQueries(queries=[_CANON_CHUNK]),
        verdict=GroundingVerdict(
            reasoning="Canon is silent on the kiss; no premise is contradicted.",
            conflicts=[],
        ),
    )
    checker = PitchGroundingChecker(llm=llm)

    verdict = checker.check(_sample_pitch(), "topic-rin", emb, db)

    assert verdict.coheres is True
    assert verdict.conflicts == []
    assert llm.verdict_calls == 1


def test_empty_fridge_short_circuits_to_pass(db):
    """No canon in the fridge -> retrieve returns [] -> the pitch PASSES without
    ever running call-2 (absence is not a conflict; the load-bearing rule)."""
    emb = _FakeEmbedder()
    # nothing indexed under this topic

    llm = _FakeLLM(
        queries=CanonQueries(queries=["Rin and Len relationship"]),
        # verdict must never be used; conflicts here would fail the test if call-2 ran
        verdict=GroundingVerdict(reasoning="should not run", conflicts=["x"]),
    )
    checker = PitchGroundingChecker(llm=llm)

    verdict = checker.check(_sample_pitch(), "empty-topic", emb, db)

    assert verdict.coheres is True
    assert verdict.conflicts == []
    assert llm.queries_calls == 1
    assert llm.verdict_calls == 0  # call-2 skipped entirely
