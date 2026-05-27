import math
import pytest

from src.rag.schemas import RetrievalQuery, RetrievalHit
from src.rag.reranker import BgeRerankerV2M3

@pytest.fixture
def relevant_hit() -> RetrievalHit:
    relevant = RetrievalHit(
        content_item_id=1,
        blueprint_id=1,
        score=0.0,
        blueprint_data={},
        niche_label="test",
        serialized_text="a cat naps on a sofa"
    )
    return relevant

@pytest.fixture
def irelevant_hit() -> RetrievalHit:
    irelevant = RetrievalHit(
        content_item_id=2,
        blueprint_id=2,
        score=0.0,
        blueprint_data={},
        niche_label="test",
        serialized_text="i like physics"
    )
    return irelevant

@pytest.fixture(scope="module")
def reranker() -> BgeRerankerV2M3:
    return BgeRerankerV2M3()

def test_model_loads(reranker: BgeRerankerV2M3):
    assert reranker.model_name == "BAAI/bge-reranker-v2-m3"

def test_rerank(reranker: BgeRerankerV2M3, relevant_hit, irelevant_hit):

    result = reranker.rerank("cat sleeping on couch", [relevant_hit, irelevant_hit], top_n=1)

    assert result[0].content_item_id == relevant_hit.content_item_id

def test_top_n(reranker: BgeRerankerV2M3):
    test_hits = [
        RetrievalHit(content_item_id=1, blueprint_id=1, score=0.0, blueprint_data={}, niche_label="test1", serialized_text="test1"),
        RetrievalHit(content_item_id=2, blueprint_id=2, score=0.0, blueprint_data={}, niche_label="test2", serialized_text="test2"),
        RetrievalHit(content_item_id=3, blueprint_id=3, score=0.0, blueprint_data={}, niche_label="test3", serialized_text="test2"),
        RetrievalHit(content_item_id=4, blueprint_id=4, score=0.0, blueprint_data={}, niche_label="test4", serialized_text="test2"),
        RetrievalHit(content_item_id=5, blueprint_id=5, score=0.0, blueprint_data={}, niche_label="test5", serialized_text="test2"),
    ]

    result = reranker.rerank(query="sample query", candidates=test_hits, top_n=3)

    assert len(result) == 3

    for a, b in zip(result, result[1:]):
        assert a.score >= b.score

def test_score_overwrite(reranker: BgeRerankerV2M3):
    hit = [RetrievalHit(content_item_id=1, blueprint_id=1, score=0.0, blueprint_data={}, niche_label="test1", serialized_text="test1")]
    reranker.rerank(query="test query", candidates=hit, top_n=1)
    assert hit[0].score != 0.0


def test_empty_candidatese(reranker: BgeRerankerV2M3):
    result = reranker.rerank(query="any query", candidates=[], top_n=5)
    assert result == []