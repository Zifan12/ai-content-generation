"""Tests for ContentWriter (Task 4 — single-shot, model-aware one-pass)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
import src.models.trend  # noqa: F401 — registers RawContentItem with Base.metadata
import src.models.transcript  # noqa: F401 — registers Transcript with Base.metadata
import src.models.niche  # noqa: F401 — registers Niche (FK target of RawContentItem)

from src.generation.content_writer import WRITER_MAX_TOKENS, SYSTEM_PROMPT, ContentWriter, _hydrate_hits
from src.generation.render_adapters.rules import RenderRules
from src.models.trend import RawContentItem
from src.models.transcript import Transcript
from src.rag.schemas import RetrievalHit
from src.schemas.generation import ContentPackage, Shot


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def rules():
    return RenderRules()


def _mock_package(*, model_cli_id: str = "WRONG", premise: str = "WRONG PREMISE") -> ContentPackage:
    """LLM-shaped package; write() must overwrite provenance fields."""
    return ContentPackage(
        shot=Shot(
            start_keyframe="Handheld phone POV, kitchen counter, glass mid-spill.",
            motion="Water freezes in place as it pours. Audio: sharp tap of ice forming.",
        ),
        model_cli_id=model_cli_id,
        premise=premise,
        mood_anchor="Cool daylight, desaturated phone footage, photoreal.",
        onscreen_text=["wait is this real??"],
        caption="I still don't know what I filmed.",
        hashtags=["surreal", "fyp"],
    )


class FakeLLM:
    def __init__(self, package: ContentPackage | None = None):
        self.last_prompt: str | None = None
        self.last_system: str | None = None
        self.last_max_tokens: int | None = None
        self._package = package or _mock_package()

    def parse(self, prompt, response_model, system=None, max_tokens=1024):
        self.last_prompt = prompt
        self.last_system = system
        self.last_max_tokens = max_tokens
        return self._package


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
    db.flush()

    db.add(
        Transcript(
            content_item_id=item1.id,
            text="TRANSCRIPT_ONE",
            source="test",
        )
    )
    db.flush()

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

    assert result[0]["transcript"] == "TRANSCRIPT_ONE"
    assert result[0]["aesthetic_descriptors"] == ["dreamcore_void", "uncanny_AAA"]
    assert result[0]["hook_subtype"] == "impossible_visual"
    assert result[1]["transcript"] is None
    assert result[1]["aesthetic_descriptors"] is None
    assert result[1]["hook_subtype"] is None
    assert "caption" not in result[0]



def test_write_code_sets_premise_and_model(rules):
    fake = FakeLLM()
    writer = ContentWriter(llm=fake)
    result = writer.write(premise="a premise", model_cli_id="veo3_1", rules=rules, hits=None)

    assert result.premise == "a premise"
    assert result.model_cli_id == "veo3_1"
    assert fake.last_system == SYSTEM_PROMPT
    assert fake.last_max_tokens == WRITER_MAX_TOKENS

def test_contract_shape(rules):
    fake = FakeLLM()
    writer = ContentWriter(llm=fake)
    result = writer.write(premise="a premise", model_cli_id="veo3_1", rules=rules, hits=None)

    assert "Audio: " in result.shot.motion 
    assert len(result.onscreen_text) >= 1


def test_write_without_hits_succeeds(rules):
    fake = FakeLLM()
    writer = ContentWriter(llm=fake)
    result = writer.write(premise="a premise", rules=rules)

    assert isinstance(result, ContentPackage)
    assert result.grounding_hit_ids == []

def test_dialect_injection(rules):
    fake = FakeLLM()
    writer = ContentWriter(llm=fake)
    _ = writer.write(premise="a premise", model_cli_id="veo3_1", rules=rules, hits=None)

    dialect = rules.still_dialect()["camera_kit"]
    veo_motion = rules.model("veo3_1")["dialect"]["style"]

    assert dialect in fake.last_prompt
    assert veo_motion in fake.last_prompt
    assert "a premise" in fake.last_prompt