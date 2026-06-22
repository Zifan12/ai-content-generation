"""
Smoke + invariant tests for BgeM3Embedder.

Module-scoped fixture loads BAAI/bge-m3 once for all tests. First test run takes
~5-10s to load from HF cache; subsequent tests reuse the loaded model.

Tests cover:
  1. Output dimension matches the pgvector schema (Vector(1024)).
  2. L2 normalization is actually applied (cosine -> dot product invariant).
  3. Batched and single-input embeddings agree (no padding-induced drift).
  4. Semantic sanity: model is loaded with the right weights, not random init.
"""

import math

import pytest

from src.rag.embedder import BgeM3Embedder


@pytest.fixture(scope="module")
def embedder() -> BgeM3Embedder:
    """
    Build one BgeM3Embedder per test module.

    Module scope keeps the model resident across all 4 tests (single ~5-10s
    load instead of 4x). Defaults match plan's locked config: model_name
    'BAAI/bge-m3', device 'auto', normalize True.
    """
    return BgeM3Embedder()


def _cosine(a: list[float], b: list[float]) -> float:
    """
    Cosine similarity for two equal-length float lists.

    Because BgeM3Embedder returns L2-normalized vectors, cosine reduces to a
    plain dot product. Used by the semantic-sanity test below.
    """
    return sum(x * y for x, y in zip(a, b))


def test_dim_is_1024(embedder: BgeM3Embedder) -> None:
    """
    Output vectors must be 1024-dim to match the viral_videos.embedding
    pgvector column. Also asserts the `dim` property contract independent
    of an actual embed call, so a future model swap with a mismatched
    property is caught immediately.
    """
    vectors = embedder.embed(["hello world"])

    assert len(vectors) == 1
    assert len(vectors[0]) == 1024
    assert embedder.dim == 1024


def test_normalized_output_unit_length(embedder: BgeM3Embedder) -> None:
    """
    Verifies normalize_embeddings=True is actually wired through to
    SentenceTransformer.encode. If the L2 norm is not ~1.0, cosine
    similarity in pgvector queries (which assumes unit vectors when using
    the dot-product operator) will silently return wrong rankings.
    """
    vector = embedder.embed(["normalization invariant check"])[0]
    norm = math.sqrt(sum(x * x for x in vector))

    assert norm == pytest.approx(1.0, abs=1e-5)


def test_batch_consistency(embedder: BgeM3Embedder) -> None:
    """
    Embedding 'alpha' inside a batch with 'beta' must yield the same vector
    as embedding 'alpha' on its own. Catches batch-padding bugs or attention
    leakage between inputs. Tolerance 1e-5 allows for minor GPU non-determinism;
    tighten to 1e-6 if the model+device combo turns out to be stable.
    """
    batch = embedder.embed(["alpha", "beta"])
    single = embedder.embed(["alpha"])

    assert batch[0] == pytest.approx(single[0], abs=1e-5)


def test_semantic_sanity(embedder: BgeM3Embedder) -> None:
    """
    Loaded weights must encode real semantics. 'dog' should be closer to
    'puppy' than to 'airplane'. Failure here typically means the wrong
    model name was loaded, weights are random-initialized, or normalization
    broke (cosine no longer meaningful).
    """
    v_dog, v_puppy, v_airplane = embedder.embed(["dog", "puppy", "airplane"])

    sim_close = _cosine(v_dog, v_puppy)
    sim_far = _cosine(v_dog, v_airplane)

    assert sim_close > sim_far
