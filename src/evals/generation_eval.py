"""
RAG-grounded vs naked-prompt generation eval for the P3 writer.

Measures `rag_win_rate`: fraction of target BlueprintCandidates where the
RAG-grounded ContentWriter output is preferred by a pairwise LLM judge over
a naked-prompt baseline (same candidate, no retrieved neighbors).

Gate: rag_win_rate >= 0.70 to ship the writer slice.
"""

import json
from pathlib import Path

from src.miner.schemas import BlueprintCandidate
from src.evals.judges import ScriptQualityJudge
from src.schemas.generation import ContentPackage
from src.rag.schemas import RetrievalQuery
from src.rag.retriever import BlueprintRetriever
from src.generation.content_writer import build_naked_envelope, SYSTEM_PROMPT, ContentWriter


def _render(package: ContentPackage) -> str:
    """
    Render a ContentPackage to a flat string for the pairwise judge.

    The device + rationale lead (the creative treatment driving the take), then the
    3 chained segments in chain order (opening → middle → closing): segment 1 emits
    its start_keyframe (the only generated still) then its motion; segments 2-3 have
    no start_keyframe (they inherit the previous clip's last frame), so they emit
    only motion, plus an end_keyframe when the segment must reach a specific state.
    Fields stay grouped by segment so the judge reads each segment's frame + motion
    together, not all frames then all motions. After the segments come the overlays,
    caption, hashtags, and optional voiceover. mood_anchor is omitted (package-level,
    one grade for the whole take — no comparative signal for the judge).
    """

    parts = []

    # The device leads — it tells the judge the creative treatment the take is built
    # on (embodiment / transformation / reveal / ...), so the segments are read
    # against their own intent rather than as a generic montage.
    parts.append(f"device: {package.device}")
    parts.append(f"device_rationale: {package.device_rationale}")

    for shot in package.shots:
        if shot.start_keyframe is not None:
            parts.append(shot.start_keyframe)
        parts.append(shot.motion)
        if shot.end_keyframe is not None:
            parts.append(shot.end_keyframe)

    parts.extend(package.onscreen_text)
    parts.append(package.caption)
    parts.extend(package.hashtags)
    if package.voiceover:
        parts.append(package.voiceover)
    return "\n".join(parts)


def generation_rag_win_rate(
    targets: list[BlueprintCandidate],
    db,
    judge: ScriptQualityJudge,
    llm,
    retriever: BlueprintRetriever,
    seed: int = 42,
) -> dict:
    """
    Compare RAG-grounded vs naked generation for each target candidate.

    For each target: retrieves neighbors, generates the grounded package via
    ContentWriter.write and a naked package from the template alone, then asks a
    pairwise judge which is better. Tallies RAG wins and returns the win rate plus
    gate verdict (gate: rag_win_rate >= 0.70).

    Args:
        targets: BlueprintCandidates to evaluate.
        db: SQLAlchemy session used for hit hydration during retrieval/generation.
        judge: ScriptQualityJudge instance (or compatible fake).
        llm: LLM with .parse(prompt, response_model, system) -> ContentPackage.
        retriever: BlueprintRetriever supplying each target's grounding neighbors.
        seed: reserved for a position-bias swap; not yet used.

    Returns:
        Dict with rag_win_rate (float), n (int), rag_wins (int), gate_passed (bool).
    """
    rag_wins = 0
    n = len(targets)
    per_item: list[dict] = []

    for target in targets:

        response = retriever.retrieve(RetrievalQuery(candidate=target))

        hits = response.hits
        rag_package = ContentWriter(llm=llm).write(target, hits, db)
        rag_str = _render(rag_package)

        naked_str = build_naked_envelope(target)
        naked_str = _render(llm.parse(naked_str, response_model=ContentPackage, system=SYSTEM_PROMPT))

        verdict = judge.judge_pairwise(
            video_stats={},
            rag_script=rag_str,
            baseline_script=naked_str,
        )

        if verdict.preferred == "rag":
            rag_wins += 1

        # Keep the per-item receipts the loop would otherwise discard: which arm
        # won, the judge's reasoning, and both rendered scripts. This is the
        # evidence layer a single rag_win_rate scalar cannot expose — read the
        # losses' reasoning to tell whether grounding is thin, the judge ignores
        # it, or the call is genuine noise.
        per_item.append({
            "rank": target.rank,
            "niche_label": target.niche_label,
            "grounding_hit_ids": rag_package.grounding_hit_ids,
            "preferred": verdict.preferred,
            "reasoning": verdict.reasoning,
            "rag_script": rag_str,
            "naked_script": naked_str,
        })

    rag_win_rate = rag_wins / n if n > 0 else 0.0

    # Dump the receipts next to other run artifacts so they can be eyeballed
    # without re-running the (paid) gate.
    out_path = Path("output/generation_eval_peritem.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for record in per_item:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {
        "rag_win_rate": rag_win_rate,
        "n": n,
        "rag_wins": rag_wins,
        "gate_passed": rag_win_rate >= 0.70,
        "per_item": per_item,
    }
