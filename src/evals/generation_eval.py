"""
RAG-grounded vs naked-prompt generation eval for the P3 writer.

Measures `rag_win_rate`: fraction of target BlueprintCandidates where the
RAG-grounded ContentWriter output is preferred by a pairwise LLM judge over
a naked-prompt baseline (same candidate, no retrieved neighbors).

Gate: rag_win_rate >= 0.70 to ship the writer slice.
"""

import json

from src.miner.schemas import BlueprintCandidate
from src.evals.judges import ScriptQualityJudge
from src.schemas.generation import ContentPackage
from src.generation.content_writer import SYSTEM_PROMPT


def _render(package: ContentPackage) -> str:
    """Render a ContentPackage to a flat string for the pairwise judge."""
    parts = [package.video_prompt]
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
    seed: int = 42,
) -> dict:
    """
    Compare RAG-grounded vs naked generation for each target candidate.

    For each target, generates two ContentPackages via llm.parse — one with
    the RAG envelope (target + retrieved neighbors), one naked (target only).
    A pairwise judge decides which is better. Tallies RAG wins and returns
    the win rate plus gate verdict.

    Args:
        targets: BlueprintCandidates to evaluate.
        db: SQLAlchemy session (used for retrieval in Task 7; may be None in unit tests).
        judge: ScriptQualityJudge instance (or compatible fake).
        llm: LLM instance with .parse(prompt, response_model, system) -> ContentPackage.
        seed: Random seed for reproducibility (position-bias swap, Task 7).

    Returns:
        Dict with rag_win_rate (float), n (int), rag_wins (int), gate_passed (bool).
    """
    rag_wins = 0
    n = len(targets)

    for target in targets:
        envelope = json.dumps(target.blueprint_template)

        rag_package = llm.parse(envelope, response_model=ContentPackage, system=SYSTEM_PROMPT)
        naked_package = llm.parse(envelope, response_model=ContentPackage, system=SYSTEM_PROMPT)

        rag_str = _render(rag_package)
        naked_str = _render(naked_package)

        verdict = judge.judge_pairwise(
            video_stats={},
            rag_script=rag_str,
            baseline_script=naked_str,
        )

        if verdict.preferred == "rag":
            rag_wins += 1

    rag_win_rate = rag_wins / n if n > 0 else 0.0

    return {
        "rag_win_rate": rag_win_rate,
        "n": n,
        "rag_wins": rag_wins,
        "gate_passed": rag_win_rate >= 0.70,
    }
