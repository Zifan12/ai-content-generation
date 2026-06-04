
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pydantic import ValidationError

from src.database import Base
import src.models.trend       # noqa: F401 — registers RawContentItem with Base.metadata
import src.models.transcript  # noqa: F401 — registers Transcript with Base.metadata
import src.models.niche       # noqa: F401 — registers Niche (FK target of RawContentItem)

from src.schemas.generation import ContentPackage
from src.miner.schemas import MinerEvidence
from src.miner.schemas import BlueprintCandidate
from src.models.trend import RawContentItem
from src.models.transcript import Transcript
from src.rag.schemas import RetrievalHit
from src.generation.content_writer import build_envelope, _hydrate_hits, ContentWriter

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session   
    session.close()
    engine.dispose()

def test_content_package_validates_minimal():
    package = ContentPackage(
        video_prompt="test",
        onscreen_text=["test", "test", "test"],
        caption="test123",
        hashtags=["test1", "test2"],
        
    )

    assert package.grounding_hit_ids == []
    assert package.voiceover is None
    assert package.rationale is None

def test_content_package_rejects_missing_video_prompt():
    with pytest.raises(ValidationError):
        ContentPackage(
        onscreen_text=["test", "test", "test"],
        caption="test123",
        hashtags=["test1", "test2"],

    )


def test_build_envelope_includes_target_and_winners():
    evidence = MinerEvidence(
        matching_items=1,
        median_views=0,
        p90_views=0,
        trend_slope_4wk_pct=0.0,
        rationale="test"
    )

    candidate = BlueprintCandidate(
        rank=1,
        niche_label="surreal_hyperreal",
        blueprint_template={"niche_label": "ITS2AMINTHEMORNING"},
        evidence=evidence,
        
    )

    # hydrated_hits now carry transcript (None when absent) + blueprint-derived
    # aesthetic_descriptors / hook_subtype. Hit 2 has NO transcript, so it must
    # still contribute its aesthetics — that proves the floor-signal fix.
    hits = [
        {
            "transcript": "SPOKEN_AAA",
            "aesthetic_descriptors": ["dreamcore_void", "uncanny_AAA"],
            "hook_subtype": "impossible_visual",
        },
        {
            "transcript": None,
            "aesthetic_descriptors": ["liminal_BBB"],
            "hook_subtype": "slow_reveal",
        },
    ]

    result = build_envelope(candidate, hits)

    assert "ITS2AMINTHEMORNING" in result          # target template present
    assert "uncanny_AAA" in result                 # hit 1 aesthetics
    assert "liminal_BBB" in result                 # hit 2 aesthetics (no transcript, still included)
    assert "SPOKEN_AAA" in result                  # hit 1 transcript present
    assert "impossible_visual" in result           # hit 1 hook subtype
    assert "Example 1" in result and "Example 2" in result  # per-winner labels
    assert "CAPTION" not in result                 # captions are no longer grounded


def test_hydrate_pulls_transcript_and_blueprint_fields(db):
    item1 = RawContentItem(
        platform="tiktok",
        platform_content_id="vid1",
        url="https://test.com/1",
        description="CAPTION_ONE",
    )
    item2 = RawContentItem(
        platform="tiktok",
        platform_content_id="vid2",
        url="https://test.com/2",
        description="CAPTION_TWO",
    )

    db.add(item1)
    db.add(item2)
    db.flush()  # assigns item1.id / item2.id before the Transcript FK + hits need them

    # Transcript linked to item1 only. item2 deliberately has none, so the
    # outerjoin must keep item2's hit and report its transcript as None (not a
    # placeholder string — absence is carried truthfully, the formatter decides
    # how to render it).
    has_transcript = Transcript(
        content_item_id=item1.id,
        text="TRANSCRIPT_ONE",
        source="test",
    )
    db.add(has_transcript)
    db.flush()

    # aesthetic_descriptors + hook_subtype are read off the hit's blueprint_data
    # (no DB round-trip). hit1 carries them; hit2's empty blueprint_data exercises
    # the missing path (-> None).
    hit1 = RetrievalHit(
        content_item_id=item1.id,
        blueprint_id=1,
        score=0.9,
        blueprint_data={
            "aesthetic_descriptors": ["dreamcore_void", "uncanny_AAA"],
            "hook_subtype": "impossible_visual",
        },
        niche_label="surreal_hyperreal",
    )
    hit2 = RetrievalHit(
        content_item_id=item2.id,
        blueprint_id=2,
        score=0.8,
        blueprint_data={},
        niche_label="surreal_hyperreal",
    )

    result = _hydrate_hits([hit1, hit2], db)

    # hit1: has transcript + populated blueprint fields
    assert result[0]["transcript"] == "TRANSCRIPT_ONE"
    assert result[0]["aesthetic_descriptors"] == ["dreamcore_void", "uncanny_AAA"]
    assert result[0]["hook_subtype"] == "impossible_visual"

    # hit2: no transcript -> None (not "(missing)"); empty blueprint -> None fields
    assert result[1]["transcript"] is None
    assert result[1]["aesthetic_descriptors"] is None
    assert result[1]["hook_subtype"] is None

    # caption is no longer hydrated at all
    assert "caption" not in result[0]

# ------------------------------------------------------------------

class FakeLLM():
     def parse(self, prompt, response_model, system=None, max_tokens=1024):
        package = ContentPackage(
        video_prompt="test",
        onscreen_text=["test", "test", "test"],
        caption="test123",
        hashtags=["test1", "test2"],
        grounding_hit_ids=[],
        )

        return package
        


def test_write_returns_package_and_sets_grounding_ids(db):

    item1 = RawContentItem(
        platform="tiktok",
        platform_content_id="vid1",
        url="https://test.com/1",
        description="CAPTION_ONE",
    )
    item2 = RawContentItem(
        platform="tiktok",
        platform_content_id="vid2",
        url="https://test.com/2",
        description="CAPTION_TWO",
    )

    db.add(item1)
    db.add(item2)
    db.flush()  


    has_transcript = Transcript(
        content_item_id=item1.id,
        text="TRANSCRIPT_ONE",
        source="test",
    )
    db.add(has_transcript)
    db.flush()

    hit1 = RetrievalHit(
        content_item_id=item1.id,
        blueprint_id=1,
        score=0.9,
        blueprint_data={},
        niche_label="surreal_hyperreal",
    )
    hit2 = RetrievalHit(
        content_item_id=item2.id,
        blueprint_id=2,
        score=0.8,
        blueprint_data={},
        niche_label="surreal_hyperreal",
    )
    hits = [hit1, hit2]

    
    evidence = MinerEvidence(
        matching_items=1,
        median_views=0,
        p90_views=0,
        trend_slope_4wk_pct=0.0,
        rationale="test"
    )

    
    candidate = BlueprintCandidate(
        rank=1,
        niche_label="surreal_hyperreal",
        blueprint_template={"niche_label": "ITS2AMINTHEMORNING"},
        evidence=evidence,
        
    )

    writer = ContentWriter(llm=FakeLLM())

    result = writer.write(candidate, hits, db)

    assert isinstance(result, ContentPackage)
    assert result.grounding_hit_ids == [h.content_item_id for h in hits]

def test_write_empty_hits_raises():

    evidence = MinerEvidence(
        matching_items=1,
        median_views=0,
        p90_views=0,
        trend_slope_4wk_pct=0.0,
        rationale="test"
    )
    candidate = BlueprintCandidate(
        rank=1,
        niche_label="surreal_hyperreal",
        blueprint_template={"niche_label": "ITS2AMINTHEMORNING"},
        evidence=evidence,
        
    )
    
    writer = ContentWriter(llm=FakeLLM())
    with pytest.raises(ValueError):
        writer.write(candidate, [], None)



