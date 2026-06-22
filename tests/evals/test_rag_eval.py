import pytest 
import hashlib
import numpy as np

from sqlalchemy.orm import Session

from src.database import engine
from src.rag.indexer import index_corpus
from src.rag.embedder import TextEmbedder
from src.rag.reranker import Reranker
from src.rag.retriever import BlueprintRetriever
from src.evals.rag_eval import mechanic_hit_at_5, mechanic_hit_at_5_ablation, TIER1_ENUM_FIELDS
from src.rag.schemas import RetrievalQuery, RetrievalHit
from src.models.blueprint import BlueprintRecord
from src.models.trend import RawContentItem
from src.models.transcript import Transcript
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

class _FakeReranker(Reranker):
    def rerank(self, query: str, candidates: list[RetrievalHit], top_n: int) -> list[RetrievalHit]:
        self.candidates = candidates

        for candidate in candidates:
            candidate.score = 99.0

        return candidates[:top_n]

    @property
    def model_name(self):
        return "fake-reranker"

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


def _seed_blueprints(db: Session, blueprint_datas: list[dict]) -> list[BlueprintRecord]:
    """Seed one RawContentItem + Transcript + BlueprintRecord trio per supplied dict.

    The caller passes the full blueprint_data for each row, so a test can engineer
    exact Tier-1 enum overlap: identical dicts cluster and retrieve their clones,
    mutually-distinct dicts stay below the hit threshold. Returns the created
    BlueprintRecords in input order.
    """
    blueprints = []
    for i, blueprint_data in enumerate(blueprint_datas):
        # Empty raw text on purpose: with description/hashtags/transcript falsy,
        # serialize_for_embed emits only the blueprint lines, so a doc's embed text
        # equals the query's serialize_candidate_for_query text for the same enums.
        # Identical-enum rows then share a vector (cosine 1.0) and cluster reliably
        # under the deterministic fake embedder.
        raw = RawContentItem(
            platform="tiktok",
            platform_content_id=f"vid{i}",
            url=f"https://tt.com/v/{i}",
            description="",
            hashtags=[],
        )
        db.add(raw)
        db.flush()

        transcript = Transcript(
            content_item_id=raw.id,
            text="",
            source="en",
        )
        db.add(transcript)
        db.flush()

        bp = BlueprintRecord(
            content_item_id=raw.id,
            extractor_version=TEST_EXTRACTOR_VERSION,
            extractor_model="fake-model",
            blueprint_data=blueprint_data,
        )
        db.add(bp)
        db.flush()

        blueprints.append(bp)

    return blueprints


def _twin_data() -> dict:
    """One blueprint_data dict whose 10 Tier-1 fields share a single value.

    Every twin gets this identical dict, so each twin retrieves the other four
    as exact clones (overlap 10 >= threshold) and passes.
    """
    data = {field: "same" for field in TIER1_ENUM_FIELDS}
    data["niche_label"] = "surreal_hyperreal"
    return data


def _loner_data(k: int) -> dict:
    """One blueprint_data dict whose 10 Tier-1 fields are all unique to loner k.

    Two loners (different k) share zero Tier-1 values, so a loner's neighbors
    never reach the 3-enum threshold and it fails.
    """
    data = {field: f"loner{k}" for field in TIER1_ENUM_FIELDS}
    data["niche_label"] = "surreal_hyperreal"
    return data


def test_engineered_pass_rate(db, fake_embedder):
    # 5 identical twins (each passes) + 5 mutually-distinct loners (each fails)
    # => predicted mechanic_hit_at_5 == 0.5
    blueprint_datas = [_twin_data() for _ in range(5)] + [_loner_data(k) for k in range(5)]
    _ = _seed_blueprints(db, blueprint_datas)
    _ = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)

    result = mechanic_hit_at_5(
        db,
        fake_embedder,
        holdout_n=10,
        seed=42,
        extractor_version=TEST_EXTRACTOR_VERSION,
    )

    assert result["mechanic_hit_at_5"] == 0.5

def test_determinism(db, fake_embedder):

    blueprint_datas = [_twin_data() for i in range(5)]
    _ = _seed_blueprints(db, blueprint_datas)
    _ = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)

    result1 = mechanic_hit_at_5(
        db, 
        fake_embedder,
        holdout_n=5,
        seed=42,
        extractor_version=TEST_EXTRACTOR_VERSION,
    )
    result2 = mechanic_hit_at_5(
        db, 
        fake_embedder,
        holdout_n=5,
        seed=42,
        extractor_version=TEST_EXTRACTOR_VERSION,
    )

    assert result1 == result2

def test_holdout_exclusion(db, fake_embedder):
    blueprint_datas = [_twin_data() for i in range(5)]
    blueprints = _seed_blueprints(db, blueprint_datas)
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

    query = RetrievalQuery(candidate=candidate, top_k=5, exclude_ids={blueprints[0].content_item_id})

    response = BlueprintRetriever(db, fake_embedder, TEST_EXTRACTOR_VERSION, reranker=None, stage_1_k=5).retrieve(query)

    assert blueprints[0].content_item_id not in [h.content_item_id for h in response.hits]

 
def test_reranker_model(db, fake_embedder):
    blueprint_datas = [_twin_data() for i in range(5)]
    _ = _seed_blueprints(db, blueprint_datas)
    _ = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)

    reranker = _FakeReranker()

    result1 = mechanic_hit_at_5(
        db, 
        fake_embedder,
        reranker=None,
        holdout_n=5,
        seed=42,
        extractor_version=TEST_EXTRACTOR_VERSION,
    )

    result2 = mechanic_hit_at_5(
        db, 
        fake_embedder,
        reranker=reranker,
        holdout_n=5,
        seed=42,
        extractor_version=TEST_EXTRACTOR_VERSION,
    )

    assert result1["reranker_model"] is None
    assert result2["reranker_model"] == reranker.model_name


def test_ablation(db, fake_embedder):
    blueprint_datas = [_twin_data() for i in range(5)]
    _ = _seed_blueprints(db, blueprint_datas)
    _ = index_corpus(db, fake_embedder, extractor_version=TEST_EXTRACTOR_VERSION)

    result = mechanic_hit_at_5_ablation(db, fake_embedder, reranker=_FakeReranker(), holdout_n=5, seed=42, stage_1_k=5, extractor_version=TEST_EXTRACTOR_VERSION)

    assert isinstance(result["vector_only"], dict)
    assert isinstance(result["with_rerank"], dict)
    assert isinstance(result["rerank_lift"], float)
    assert isinstance(result["gate_passed"], bool)
    assert result["vector_only"]  == mechanic_hit_at_5(db, fake_embedder, reranker=None, holdout_n=5, seed=42, stage_1_k=5, extractor_version=TEST_EXTRACTOR_VERSION)