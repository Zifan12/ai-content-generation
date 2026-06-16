import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
import src.models.niche       # noqa: F401 — registers Niche
import src.models.trend       # noqa: F401 — registers RawContentItem

from src.models.niche import Niche
from src.models.trend import RawContentItem
from src.miner.schemas import BlueprintCandidate, MinerEvidence
from src.schemas.premise import Premise, PremiseSet
from src.generation.premise_generator import (
    PremiseGenerator,
    _top_winners,
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


def _add_niche(db, name: str) -> Niche:
    niche = Niche(name=name, keywords=[], hashtag_seeds=[])
    db.add(niche)
    db.flush()
    return niche


def _add_item(db, *, niche: Niche, views: int, description: str, platform_content_id: str) -> RawContentItem:
    item = RawContentItem(
        platform="tiktok",
        platform_content_id=platform_content_id,
        url=f"https://test.com/{platform_content_id}",
        niche_id=niche.id,
        views=views,
        description=description,
        hashtags=["#test"],
    )
    db.add(item)
    db.flush()
    return item


def _sample_candidate() -> BlueprintCandidate:
    evidence = MinerEvidence(
        matching_items=1,
        median_views=0,
        p90_views=0,
        trend_slope_4wk_pct=0.0,
        rationale="test",
    )
    return BlueprintCandidate(
        rank=1,
        niche_label="surreal_hyperreal",
        blueprint_template={"niche_label": "surreal_hyperreal", "hook_type": "slow_reveal"},
        evidence=evidence,
    )


def _sample_premise_set() -> PremiseSet:
    return PremiseSet(
        premises=[
            Premise(
                premise="A hallway mirror shows a room that is not behind you.",
                winning_mechanics="liminal-breach — echoes Winner 1's impossible interior.",
                copies_nothing="Uses a mirror, not a staircase or doorway from the winners.",
            ),
            Premise(
                premise="A bathtub fills with sand while the tap still runs water.",
                winning_mechanics="uncanny-domestic — ordinary bathroom, impossible fill.",
                copies_nothing="Bathtub subject, not any winner's object or setting.",
            ),
            Premise(
                premise="Streetlights turn on one by one in daylight on an empty road.",
                winning_mechanics="perceptual-doubt — trusted scene behaves wrongly.",
                copies_nothing="Outdoor road, not indoor winner locations.",
            ),
            Premise(
                premise="A child's drawing on the fridge updates before anyone touches it.",
                winning_mechanics="inescapable-loop — change keeps happening off-screen.",
                copies_nothing="Fridge art, not winner subjects or reveals.",
            ),
            Premise(
                premise="An elevator arrives with the floor number counting backward.",
                winning_mechanics="liminal-breach — familiar transit space goes wrong.",
                copies_nothing="Elevator, not winner settings or props.",
            ),
        ]
    )


class FakeLLM:
    def __init__(self):
        self.last_envelope: str | None = None
        self.last_system: str | None = None

    def parse(self, prompt, response_model, system=None, max_tokens=1024):
        self.last_envelope = prompt
        self.last_system = system
        return _sample_premise_set()


def test_top_winners_filters_niche_orders_by_views_and_limits_k(db):
    surreal = _add_niche(db, "surreal_hyperreal")
    brainrot = _add_niche(db, "brainrot")

    _add_item(db, niche=surreal, views=100, description="LOW_SURREAL", platform_content_id="s1")
    _add_item(db, niche=surreal, views=500, description="MID_SURREAL", platform_content_id="s2")
    _add_item(db, niche=surreal, views=2_000, description="TOP_SURREAL", platform_content_id="s3")
    # Trap row: highest views globally but wrong niche — must be excluded.
    _add_item(db, niche=brainrot, views=9_999_999, description="TRAP_BRAINROT", platform_content_id="b1")

    result = _top_winners(db, "surreal_hyperreal", k=2)

    assert len(result) == 2
    assert [row.views for row in result] == [2_000, 500]
    assert [row.description for row in result] == ["TOP_SURREAL", "MID_SURREAL"]
    assert all(row.niche_id == surreal.id for row in result)


def test_generate_passes_winners_into_envelope(db):
    surreal = _add_niche(db, "surreal_hyperreal")
    _add_item(db, niche=surreal, views=1_000, description="MELTING_STAIRCASE_WINNER", platform_content_id="w1")
    _add_item(db, niche=surreal, views=500, description="AGING_REFLECTION_WINNER", platform_content_id="w2")

    fake = FakeLLM()
    generator = PremiseGenerator(llm=fake)

    result = generator.generate(_sample_candidate(), db, "surreal_hyperreal", k=2)

    assert isinstance(result, PremiseSet)
    assert len(result.premises) == 5
    assert fake.last_envelope is not None
    assert "MELTING_STAIRCASE_WINNER" in fake.last_envelope
    assert "AGING_REFLECTION_WINNER" in fake.last_envelope
    assert "Winner 1" in fake.last_envelope
    assert fake.last_system is not None