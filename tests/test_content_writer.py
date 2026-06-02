
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
        package = ContentPackage(
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

    hits = [{"caption": "CAPTION_AAA"}, {"caption": "CAPTION_BBB"}]

    result = build_envelope(candidate, hits)

    assert "CAPTION_AAA" in result
    assert "CAPTION_BBB" in result
    assert "ITS2AMINTHEMORNING" in result


def test_hydrate_pulls_caption_and_marks_missing_transcript(db):
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
    # outerjoin must keep item2's hit and mark its transcript "(missing)".
    has_transcript = Transcript(
        content_item_id=item1.id,
        text="TRANSCRIPT_ONE",
        source="test",
    )
    db.add(has_transcript)
    db.flush()

    # Non-id fields are irrelevant to hydration (it only reads content_item_id
    # to look up the DB), so they carry throwaway fakes.
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

    result = _hydrate_hits([hit1, hit2], db)

    assert result[0]["caption"] == "CAPTION_ONE"
    assert result[0]["transcript"] == "TRANSCRIPT_ONE"
    assert result[1]["caption"] == "CAPTION_TWO"
    assert result[1]["transcript"] == "(missing)"

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



