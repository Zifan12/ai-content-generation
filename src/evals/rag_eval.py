"""Leave-one-out retrieval quality eval for the P2 RAG stack.

Measures `mechanic_hit_at_5`: the fraction of held-out blueprints for which
the retriever surfaces a mechanically-similar neighbor in its top 5. This is
the P2 gate — without it, prompt/serialization/reranker changes silently
degrade retrieval and nothing downstream notices until generation quality
drops. Uses no human labels: each held-out row is its own query, excluded
from its own candidate set so it can't trivially retrieve itself.
"""

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.miner.schemas import MinerEvidence, BlueprintCandidate
from src.rag.embedder import TextEmbedder
from src.rag.reranker import Reranker
from src.models.blueprint import BlueprintRecord
from src.rag.retriever import RetrievalQuery, RetrievalResponse, BlueprintRetriever

# Superset of ADR-0003's 8 Tier-1 mechanics plus primary_emotion + duration_band:
# the eval's similarity signal is intentionally broader than the extractor's
# mechanic tier — both extra fields are closed enums and carry real similarity signal.
TIER1_ENUM_FIELDS = [
    "hook_type", "share_hook_type", "comment_bait_type",
    "pacing", "loop_type", "audio_type",
    "visual_complexity", "color_mood",
    "primary_emotion", "duration_band",
]

def mechanic_hit_at_5(
    db: Session,
    embedder: TextEmbedder,
    reranker: Reranker | None = None,
    holdout_n: int = 30,
    min_shared_enums: int = 3,
    seed: int = 42,
    stage_1_k: int = 20,
    extractor_version: str = "v3.1",
) -> dict:
    """Score retrieval quality by leave-one-out mechanic overlap.

    Samples `holdout_n` BlueprintRecords (deterministic via `seed`). For each
    held-out row, builds a query from its Tier-1 enums, excludes the row from
    the candidate set so it can't retrieve itself, retrieves the top 5, and
    counts the row as a "hit" if at least one neighbor shares `min_shared_enums`
    or more TIER1_ENUM_FIELDS values with it. The metric is hits / holdout_n.

    Args:
        reranker: when None, scores the vector-only path; when passed, runs the
            two-stage rerank path. The caller decides which shape to measure.
        min_shared_enums: overlap threshold for a neighbor to count as a hit.
        stage_1_k: stage-1 pool width handed to the reranker (ignored when
            reranker is None).

    Returns:
        Dict with the headline `mechanic_hit_at_5` float, `holdout_n`, a
        `per_item_results` list (one {content_item_id, passed, shared_enums_max}
        per held-out row), and run metadata (seed, embedder/reranker model,
        stage_1_k).
    """

    stmt = (
        select(BlueprintRecord)
        .where(BlueprintRecord.extractor_version == extractor_version)

    )

    records = db.execute(stmt).scalars().all()

    random.seed(seed)
    holdout_records = random.sample(records, holdout_n)

    retriever = BlueprintRetriever(db=db, embedder=embedder,reranker= reranker, stage_1_k=stage_1_k, extractor_version=extractor_version)

    per_item_results = []
    pass_count = 0
    for record in holdout_records:
        blueprint_template = {field: record.blueprint_data.get(field) for field in TIER1_ENUM_FIELDS}
        
        evidence = MinerEvidence(
            matching_items=1,
            median_views=0,
            p90_views=0,
            trend_slope_4wk_pct=0.0,
            rationale="eval stub"
        )
        
        candidate = BlueprintCandidate(
            rank=1, 
            niche_label=record.blueprint_data["niche_label"], 
            blueprint_template=blueprint_template, 
            evidence=evidence,
        )

        query = RetrievalQuery(candidate=candidate, top_k=5, exclude_ids={record.content_item_id})
        response = retriever.retrieve(query)

        shared_max = 0
    
        for hit in response.hits:
            count = 0
            for field in TIER1_ENUM_FIELDS:
                count += 1 if record.blueprint_data[field] == hit.blueprint_data[field] and hit.blueprint_data[field] is not None else 0

            shared_max = max(shared_max, count)

        if shared_max >= min_shared_enums:
            passed = True
            pass_count += 1
        else:
            passed = False

        per_item_results.append({
            "content_item_id": record.content_item_id,
            "passed": passed,
            "shared_enums_max": shared_max

        })
    

    return {
        "mechanic_hit_at_5": pass_count / holdout_n,
        "holdout_n": holdout_n,
        "per_item_results": per_item_results,
        "seed": seed,
        "embedder_model": embedder.model_name,
        "reranker_model": None if reranker is None else reranker.model_name,
        "stage_1_k": stage_1_k,
    }



def mechanic_hit_at_5_ablation(
    db: Session,
    embedder: TextEmbedder,
    reranker: Reranker,
    holdout_n: int = 30,
    min_shared_enums: int = 3,
    seed: int = 42,
    stage_1_k: int = 20,
    extractor_version: str = "v3.1"
) -> dict:
    """Run the eval twice on the same holdout sample to isolate reranker lift.

    Calls mechanic_hit_at_5 with the same seed once vector-only (reranker=None)
    and once with the reranker, so both shapes test the identical held-out rows.
    Returns both result dicts plus `rerank_lift` (with_rerank − vector_only score)
    and `gate_passed` (with_rerank score >= 0.7, the P2→P3 gate).
    """

    vector_only = mechanic_hit_at_5(db, embedder, reranker=None, holdout_n=holdout_n, min_shared_enums=min_shared_enums, seed=seed, stage_1_k=stage_1_k, extractor_version=extractor_version)
    with_rerank = mechanic_hit_at_5(db, embedder, reranker=reranker, holdout_n=holdout_n, min_shared_enums=min_shared_enums, seed=seed, stage_1_k=stage_1_k, extractor_version=extractor_version)

    return {
        "vector_only": vector_only,
        "with_rerank": with_rerank,
        "rerank_lift": with_rerank["mechanic_hit_at_5"] - vector_only["mechanic_hit_at_5"],
        "gate_passed": with_rerank["mechanic_hit_at_5"] >= 0.7, 
    }








