"""
THROWAWAY cheap diagnostic: inspect retrieval quality alone (no LLM).

For the first few golden targets, runs ONLY the retriever (BGE-M3 embed +
reranker) and prints what real videos it surfaced — score, niche, and caption —
next to the target's requested mechanics. Zero Sonnet calls, zero API spend:
this answers "are the grounding examples relevant, or is rag being grounded on
garbage?" (layer-1 / retrieval check) before we spend on the full instrumented
eval.

Run:
    $env:PYTHONIOENCODING='utf-8'
    .venv\\Scripts\\python.exe -m scripts.peek_retrieval
"""

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("config/.env")

from sqlalchemy import select  # noqa: E402

from src.database import SessionLocal  # noqa: E402
from src.models.trend import RawContentItem  # noqa: E402
from src.models.transcript import Transcript  # noqa: E402
from src.miner.schemas import BlueprintCandidate  # noqa: E402
from src.rag.embedder import BgeM3Embedder  # noqa: E402
from src.rag.reranker import BgeRerankerV2M3  # noqa: E402
from src.rag.retriever import BlueprintRetriever  # noqa: E402
from src.rag.schemas import RetrievalQuery  # noqa: E402

TARGETS_PATH = Path("data/golden/generation_targets.jsonl")
EXTRACTOR_VERSION = "v3.1"
N_TARGETS = 5
TOP_K = 5


def load_targets(path: Path, n: int) -> list[BlueprintCandidate]:
    """Read the first n golden targets into BlueprintCandidate objects."""
    targets = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            targets.append(BlueprintCandidate.model_validate(json.loads(line)))
            if len(targets) >= n:
                break
    return targets


def hydrate_lookup(db, ids: list[int]) -> dict[int, tuple[str, str]]:
    """Map content_item_id -> (description, transcript) for the given ids.

    Outer-joins Transcript so items with no transcript still appear, with a
    placeholder. Mirrors the join _hydrate_hits uses, but surfaces both fields
    so we can compare caption-signal vs transcript-signal side by side.
    """
    rows = db.execute(
        select(RawContentItem.id, RawContentItem.description, Transcript.text)
        .outerjoin(Transcript, RawContentItem.id == Transcript.content_item_id)
        .where(RawContentItem.id.in_(ids))
    ).all()
    return {
        id_: (desc or "(null description)", text or "(no transcript)")
        for id_, desc, text in rows
    }


def _clip(text: str, limit: int) -> str:
    """Flatten whitespace and clip to limit chars for terminal display."""
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def main() -> None:
    targets = load_targets(TARGETS_PATH, N_TARGETS)
    print(f"Loaded {len(targets)} targets. Building retriever stack...\n")

    db = SessionLocal()
    try:
        embedder = BgeM3Embedder()
        reranker = BgeRerankerV2M3()
        retriever = BlueprintRetriever(
            db=db,
            embedder=embedder,
            extractor_version=EXTRACTOR_VERSION,
            reranker=reranker,
            stage_1_k=20,
            view_floor=100000
        )

        for target in targets:
            print("=" * 70)
            print(f"TARGET rank={target.rank}  niche={target.niche_label}")
            print(f"  mechanics: {target.blueprint_template}")
            print("-" * 70)

            response = retriever.retrieve(RetrievalQuery(candidate=target, top_k=TOP_K))
            hits = response.hits
            hydrated = hydrate_lookup(db, [h.content_item_id for h in hits])

            print(f"  retrieved {len(hits)} hits (elapsed {response.elapsed_ms:.0f} ms):")
            for rank, hit in enumerate(hits, 1):
                description, transcript = hydrated.get(
                    hit.content_item_id, ("(missing)", "(missing)")
                )
                # The hit's own extracted mechanics — the structured signal that is
                # always present (it's why the item is in the corpus at all).
                bp = hit.blueprint_data
                hook = bp.get("hook_type")
                aesthetics = bp.get("aesthetic_descriptors")
                print(
                    f"    {rank}. id={hit.content_item_id} "
                    f"score={hit.score:.3f} niche={hit.niche_label}"
                )
                print(f"       caption:    {_clip(description, 200)}")
                print(f"       transcript: {_clip(transcript, 200)}")
                print(f"       mechanics:  hook_type={hook}  aesthetics={aesthetics}")
            print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
