import pytest 
import hashlib
import numpy as np

from sqlalchemy.orm import Session

from src.database import engine
from src.rag.indexer import index_corpus
from src.rag.embedder import TextEmbedder
from src.rag.retriever import BlueprintRetriever
from src.rag.schemas import RetrievalQuery 
from src.models.blueprint import BlueprintRecord
from src.models.trend import RawContentItem
from src.models.viral_video import ViralVideo
from src.miner.schemas import MinerEvidence
from src.miner.schemas import BlueprintCandidate

TEST_EXTRACTOR_VERSION = "test-v0"

class _FakeEmbedder(TextEmbedder):
    def embed(self, texts: list[str]):
        
        vectors = []
        for text in texts:
            text_hash = hashlib.sha256(text.encode()).digest()
            seed = int.from_bytes(text_hash[:8], "little")
            seed_rng = np.random.default_rng(seed)
            vectors.append(seed_rng.standard_normal(1024).tolist())

        return vectors
        
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
    blueprints = []
    for i in range(n):
        raw = RawContentItem(
            platform="tiktok",
            platform_content_id=f"vid{i}",
            url=f"https://tt.com/v/{i}",
        )
        db.add(raw)
        db.flush()

        bp = BlueprintRecord(
            content_item_id=raw.id,
            extractor_version=TEST_EXTRACTOR_VERSION,
            extractor_model="fake-model",
            blueprint_data={"hook_type": f"shock_{i}", "primary_emotion": "awe", "niche_label": "surreal_hyperreal"},
        )
        db.add(bp)
        db.flush()

        blueprints.append(bp)

    return blueprints


def test_self_retrieval_ranks_first(db, fake_embedder):
    blueprints = _seed_blueprints(db, 3)
    _ = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)

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
        blueprint_template=blueprints[0].blueprint_data,
        evidence=evidence,
    )

    query = RetrievalQuery(
        candidate=candidate,
        top_k=5,
    )

    retriever = BlueprintRetriever(db, fake_embedder, TEST_EXTRACTOR_VERSION)
    response = retriever.retrieve(query)

    assert response.hits[0].content_item_id == blueprints[0].content_item_id

def test_hits(db, fake_embedder):
    blueprints = _seed_blueprints(db, 10)
    _ = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)

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
        blueprint_template=blueprints[0].blueprint_data,
        evidence=evidence,
    )

    query = RetrievalQuery(
        candidate=candidate,
        top_k=3,
    )

    retriever = BlueprintRetriever(db, fake_embedder, TEST_EXTRACTOR_VERSION)
    response = retriever.retrieve(query)

    assert len(response.hits) == 3

def test_score_non_increasing(db, fake_embedder):
    blueprints = _seed_blueprints(db, 10)
    _ = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)

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
        blueprint_template=blueprints[0].blueprint_data,
        evidence=evidence,
    )

    query = RetrievalQuery(
        candidate=candidate,
        top_k=3,
    )

    retriever = BlueprintRetriever(db, fake_embedder, TEST_EXTRACTOR_VERSION)
    response = retriever.retrieve(query)

    for a, b in zip(response.hits, response.hits[1:]):
        assert a.score >= b.score

def test_latency(db, fake_embedder):
    blueprints = _seed_blueprints(db, 10)
    _ = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)

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
        blueprint_template=blueprints[0].blueprint_data,
        evidence=evidence,
    )

    query = RetrievalQuery(
        candidate=candidate,
        top_k=3,
    )

    retriever = BlueprintRetriever(db, fake_embedder, TEST_EXTRACTOR_VERSION)

    response1 = retriever.retrieve(query)
    response2 = retriever.retrieve(query)

    assert response2.elapsed_ms < 50