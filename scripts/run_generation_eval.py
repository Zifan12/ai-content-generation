"""
THROWAWAY Task 7 driver: run the real generation_rag_win_rate gate.

Runs the P3 writer eval ONCE against the real stack — Postgres + BGE-M3 +
reranker retriever + Sonnet writer + Sonnet pairwise judge — over the 20
golden targets in data/golden/generation_targets.jsonl. Prints the result
dict. Not a pytest, not a CI gate: a one-shot real run whose number we record
by hand in docs/learnings/.

COST / PREREQS (read before running):
  - ~60 Sonnet calls: each of 20 targets does a RAG write + a naked write +
    one pairwise judge call. Plus 20 GPU retrievals (embed + rerank).
  - Postgres `aicg-postgres` must be up on :5433 (config/.env DATABASE_URL).
  - config/.env must hold ANTHROPIC_API_KEY.
  - BGE-M3 (~2.27GB) + bge-reranker-v2-m3 load onto the GPU. Close other GPU
    apps first — batch=8 is the safe ceiling on the local 4070.

Run:
    $env:PYTHONIOENCODING='utf-8'
    .venv\\Scripts\\python.exe -m scripts.run_generation_eval
"""

import json
from pathlib import Path

from dotenv import load_dotenv

# Load secrets BEFORE importing src.database (it reads DATABASE_URL at import).
load_dotenv("config/.env")

from src.database import SessionLocal  # noqa: E402
from src.miner.schemas import BlueprintCandidate  # noqa: E402
from src.rag.embedder import BgeM3Embedder  # noqa: E402
from src.rag.reranker import BgeRerankerV2M3  # noqa: E402
from src.rag.retriever import BlueprintRetriever  # noqa: E402
from src.providers.llm.anthropic_llm import AnthropicLLM  # noqa: E402
from src.evals.judges import ScriptQualityJudge  # noqa: E402
from src.evals.generation_eval import generation_rag_win_rate  # noqa: E402

TARGETS_PATH = Path("data/golden/generation_targets.jsonl")
EXTRACTOR_VERSION = "v3.1"
WRITER_MODEL = "claude-sonnet-4-6"


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
    print(f"Loaded {len(targets)} targets from {TARGETS_PATH}")

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
        )
        llm = AnthropicLLM(model=WRITER_MODEL)
        judge = ScriptQualityJudge(model=WRITER_MODEL)

        print("Stack constructed. Running gate (this makes ~60 Sonnet calls)...\n")

        result = generation_rag_win_rate(
            targets=targets,
            db=db,
            judge=judge,
            llm=llm,
            retriever=retriever,
            seed=42,
        )

        print("=" * 60)
        print(json.dumps(result, indent=2))
        print("=" * 60)
        verdict = "PASS" if result["gate_passed"] else "FAIL"
        print(f"\nGate (rag_win_rate >= 0.70): {verdict}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
