import pytest 

from sqlalchemy.orm import Session

from src.database import engine
from src.rag.indexer import index_corpus
from src.rag.embedder import TextEmbedder
from src.models.blueprint import BlueprintRecord
from src.models.trend import RawContentItem
from src.models.viral_video import ViralVideo

TEST_EXTRACTOR_VERSION = "test-v0"

class _FakeEmbedder(TextEmbedder):
    def embed(self, texts): 
        return [ [0.1] * 1024 for _ in texts]

    @property
    def dim(self):
        return 1024
    
    @property
    def model_name(self):
        return "fake-embedder"
    
@pytest.fixture
def fake_embedder():
    return _FakeEmbedder()


@pytest.fixture
def db():
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    trans.rollback()
    connection.close()


def _seed_blueprints(db: Session, n: int = 10) -> list[BlueprintRecord]:
    """
    Insert n (RawContentItem, BlueprintRecord) row pairs into the session.

    Each row has unique `platform_content_id` and `blueprint_data.hook_type` so
    `serialize_for_embed` produces a distinct text (and thus distinct hash) per row.
    This prevents accidental hash collisions from masking dedup bugs.

    Returns the list of inserted BlueprintRecord rows. Tests can re-query the
    matching RawContentItem via `bp.content_item_id` if needed.
    """
    blueprints = []
    for i in range(n):
        raw = RawContentItem(
            platform="tiktok",
            platform_content_id=f"vid{i}",
            url=f"https://tt.com/v/{i}",
            description=f"desc {i}",
            hashtags=[f"tag{i}"],
        )
        db.add(raw)
        db.flush()

        bp = BlueprintRecord(
            content_item_id=raw.id,
            extractor_version=TEST_EXTRACTOR_VERSION,
            extractor_model="fake-model",
            blueprint_data={"hook_type": f"shock_{i}", "primary_emotion": "awe"},
        )
        db.add(bp)
        db.flush()

        blueprints.append(bp)

    return blueprints


def test_fresh_db_embeds_all(db, fake_embedder):

    _ = _seed_blueprints(db, 10)
    result = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)

    assert result["considered"] == 10
    assert result["embedded"] == 10
    assert result["skipped_same_hash"] == 0

def test_reindex_skips_unchanged(db, fake_embedder):
    _ = _seed_blueprints(db, 10)
    _ = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)
    result2 = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)
    
    assert result2["considered"] == 10
    assert result2["embedded"] == 0
    assert result2["skipped_same_hash"] == 10

def test_mutate_one_triggers_partial_reindex(db, fake_embedder):
    blueprints = _seed_blueprints(db, 10)
    _ = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)

    blueprints[0].blueprint_data = {"hook_type": "completely_new", "primary_emotion": "fear"}

    db.flush()
    result2 = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)

    assert result2["considered"] == 10
    assert result2["embedded"] == 1
    assert result2["skipped_same_hash"] == 9

