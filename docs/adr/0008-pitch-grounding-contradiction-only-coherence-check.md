# Pitch grounding is a contradiction-only coherence check, not a faithfulness check or agent

A Story Pitch is a **wish** (or satire): it deliberately invents a moment that never happened in the source — that invention IS the product. The obvious "is the pitch grounded in the source?" framing therefore backfires: a fidelity/NLI check flags every invented moment as unsupported, and an "unsupported claims" fact-check kills exactly the content we want to make. The real failure we must catch is different: a pitch that is *incoherent* with canon — siblings written as lovers — which a fan rejects as nonsense. This ADR locks the shape of that check (`src/monitor/pitch_grounding.py`, wired Path B only) so the counter-intuitive parts are not re-litigated.

1. **Contradiction-only, never absence.** The check fails a pitch ONLY when the retrieved canon directly CONTRADICTS a premise the pitch assumes; canon that is merely SILENT (the invented moment) PASSES. Maps to NLI labels: Contradiction=fail, Neutral(silent)=pass, Entailment=pass. The accepted, permanent consequence is a conservative ceiling: the check can only catch a contradiction whose contradicting fact is actually present in the retrieved fridge canon — it will miss conflicts the research never gathered. This is a known limit, not a defect to fix.

2. **Canon = the retrieved Web-research Fridge chunks.** The check has no source-of-truth beyond what was gathered this run and indexed into the fridge (web-text only, within-run). No external canon DB, no model world-knowledge is trusted as canon.

3. **A fixed 2-call RAG pipeline, not an agent.** call-1 derives the assumed-canon premises as retrieval queries → `retrieve()` → call-2 judges contradiction-only → `{coheres, conflicts}`. The lookups are all knowable from the pitch text upfront, so no query depends on a prior retrieval's *result* — the task does not reach the agent tier (Second Brain agent-vs-pipeline consult, 2026-07-10). A judge that both selects its own evidence and rules on it also collapses retrieval-eval into judge-eval; a fixed pipeline keeps query-derivation separate and inspectable.

4. **No web-research-on-conflict in v1.** When a conflict is found, the pipeline does NOT go gather more evidence to confirm it. That would turn the fixed pipeline into an agent loop (see 3) and spend Apify/Tavily money mid-check. The cheaper first upgrade, if real runs show false contradictions, is to raise the retrieval `k` (give the judge fuller canon) — the agentic re-search is deferred behind a demonstrated multi-hop failure.

## Consequences

The check is safe to run on every wish/satire pitch without false-flagging the invention, and its verdict (`grounding_verdict_json` on `AnglePitchRecord`) is a durable, queryable record of *why* a pitch was killed. The cost is the coverage ceiling in rule 1 and the deferred upgrades in 3-4. Reversing any rule is cheap code-wise but re-opens the framing confusion this ADR exists to close (the "faithfulness / unsupported-claims" framing was tried and abandoned).

## Cost governance (ADR-0007)

The fridge + grounding check introduce **no new ungoverned paid site**. The indexing embed (BGE-M3) and retrieval (pgvector) are local — zero dollar cost. The two grounding LLM calls are governed exactly like every peer seat: a per-caller `max_tokens` cap, not a dollar guard (no LLM call in this pipeline has a dollar guard; those exist only for Apify), with call count bounded by construction (≤ top_n events × ≤3 pitches × ≤2 rounds). The only path that would hit a new paid API — web-research-on-conflict (rule 4) — is deferred, and ADR-0007 applies to it if/when it is built.

## Considered alternatives

**Faithfulness / NLI entailment check** — rejected: entailment is the wrong relation for invented-but-coherent content; it false-flags every wish. NLI dropped entirely.

**Agent-judge that gathers its own evidence** — deferred: only justified by a demonstrated multi-hop failure; it also makes retrieval quality and judge quality inseparable, so a sound verdict can't be told from a cherry-picked one.

**Search the web to confirm a conflict before acting** — deferred (rule 4): agent-loop cost + paid spend mid-check; raise `k` first.
