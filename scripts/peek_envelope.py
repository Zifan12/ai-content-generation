"""
THROWAWAY diagnostic: print the grounded envelope for a single golden target.

Builds the real retriever stack (BGE-M3 + reranker + Postgres), retrieves the
neighbors for ONE target, runs the exact hydrate + build_envelope path that
ContentWriter.write feeds to Sonnet, and prints the resulting user-prompt string.
No writer call, no judge call, zero API spend.

Purpose: prove whether the caption->aesthetics grounding fix actually reaches the
prompt. If this string carries aesthetic descriptors and no hashtag soup, the fix
is wired and a repeated 0.4 gate is genuine; if it still looks like the old junk,
the fix is not being exercised.

Run:
    $env:PYTHONIOENCODING='utf-8'
    .venv\\Scripts\\python.exe -m scripts.peek_envelope
"""

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("config/.env")

from src.database import SessionLocal  # noqa: E402
from src.miner.schemas import BlueprintCandidate  # noqa: E402
from src.rag.embedder import BgeM3Embedder  # noqa: E402
from src.rag.reranker import BgeRerankerV2M3  # noqa: E402
from src.rag.retriever import BlueprintRetriever  # noqa: E402
from src.rag.schemas import RetrievalQuery  # noqa: E402
from src.generation.content_writer import _hydrate_hits, build_envelope  # noqa: E402

TARGETS_PATH = Path("data/golden/generation_targets.jsonl")
EXTRACTOR_VERSION = "v3.1"
TARGET_INDEX = 0
TOP_K = 5


def load_targets(path: Path) -> list[BlueprintCandidate]:
    """Read the golden targets JSONL into BlueprintCandidate objects, in file order."""
    targets = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            targets.append(BlueprintCandidate.model_validate(json.loads(line)))
    return targets


def main() -> None:
    targets = load_targets(TARGETS_PATH)
    target = targets[TARGET_INDEX]
    print(f"Target index {TARGET_INDEX}: rank={target.rank} niche={target.niche_label}")
    print(f"  mechanics: {target.blueprint_template}\n")

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
            view_floor=100000,
        )

        response = retriever.retrieve(RetrievalQuery(candidate=target, top_k=TOP_K))
        hits = response.hits
        print(f"Retrieved {len(hits)} hits (elapsed {response.elapsed_ms:.0f} ms). "
              f"ids={[h.content_item_id for h in hits]}\n")

        hydrated = _hydrate_hits(hits, db)
        envelope = build_envelope(target, hydrated)

        print("=" * 70)
        print("ENVELOPE (exact string ContentWriter.write feeds to Sonnet):")
        print("=" * 70)
        print(envelope)
        print("=" * 70)
        print(f"\nEnvelope length: {len(envelope)} chars")
    finally:
        db.close()


if __name__ == "__main__":
    main()
