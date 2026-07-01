# "Hybrid retrieval" has no lexical arm — P2 claim vs code gap

Status: needs-triage
Severity: High (AUD-H16; claim-integrity, not a runtime bug)

`BlueprintRetriever.retrieve()` is pure dense cosine ANN (BGE-M3 → pgvector HNSW) + cross-encoder reranker. No BM25 stage exists anywhere in `src/` — verified by full reads of all six `src/rag/` files plus negative grep. Yet `rank-bm25` is an installed dependency and CLAUDE.md/PLAN.md describe P2 as "hybrid search: rank-bm25 + BGE-reranker" — and P2's portfolio narrative (primary project goal) cites hybrid retrieval as a demonstrated skill.

Options:
- **A (build it):** BM25 candidate set over blueprint serialization text, unioned with dense top-K, RRF fusion, then the existing reranker — the standard shape; reranker stage needs no change. Genuine learning value (the portfolio point of P2).
- **B (re-scope the claim):** amend CLAUDE.md/PLAN to "dense + rerank"; drop `rank-bm25` from deps.

Worst option is the current state: the claim-vs-code gap is exactly what an interviewer probing the portfolio would find. Needs-triage: user's call, this is roadmap scope not a defect.

## Comments
