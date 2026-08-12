# Drop the P4 virality predictor and the Blueprint corpus lane that fed it

P4 was specified as: extract structured Blueprints from the ~72k-video scraped TikTok archive, mine mechanic combinations, and train a LightGBM model on those features to predict which ideas will perform. Everything upstream of it — `src/scrapers/`, `src/enrichment/`, `src/blueprints/`, `src/miner/`, and the Blueprint half of `src/rag/` — exists to serve that pipeline. The roadmap (Modified C, locked 2026-04-29) and the hybrid-monetization strategy (locked 2026-06-09) both treat the labelled archive plus the P4 predictor as the fallback commercial wedge if content revenue does not materialize.

This ADR records the decision to drop P4 as specified and delete the corpus lane that feeds it.

## Trigger

The product moved out from under the design. The lane that actually runs today is: a named subject → Exilus research front-end (Topic Brief, Faction Map, idea slate) → staged director → a single Seedance generation, currently in the POV first-person register. None of it reads a Blueprint, and none of it retrieves from the archive.

The reason for the split is not neglect, it is domain mismatch:

1. **The corpus and the product are different distributions.** Blueprints encode the viral mechanics of *scraped human TikToks* — hook patterns, caption structure, trend participation. The output is a POV first-person AI render with no on-screen text, no voiceover, and one continuous moment. A model fit to the first population does not transfer to the second; the features it ranks on are mostly absent from what we now ship.
2. **The label path never needed Blueprints.** P4's labels come from `outcome_view_percentile` — self-relative percentiles over *our own* posted clips, produced by the publish loop (`record_post.py` → `enter_views.py` → `compute_percentiles.py`). That path is independent of the archive. The Blueprint feature set was the input half, and it is the half that no longer matches.
3. **The extraction lane already stopped.** Archive ingest was a one-time run (2026-06-09) and paid Blueprint extraction was deferred indefinitely. The corpus has not grown or been re-extracted since.

Keeping the code because a strategy note said "fallback wedge" inverts the order — the note describes a world where the product still resembled the corpus. It doesn't.

## Decision

1. **P4-as-specified is dropped.** No LightGBM model trained on Blueprint features. `src/ml/` is removed from the planned architecture (it was never created).
2. **The corpus lane is deleted**, not parked: `src/blueprints/`, `src/miner/`, `src/scrapers/`, `src/enrichment/`, the Blueprint retrieval stack (`src/rag/retriever.py`, `reranker.py`, `indexer.py`, `serialization.py`, `schemas.py`), `src/evals/blueprint_eval.py`, their tests, their maintenance scripts, and the `blueprint_extractor` seat in `config/providers.yaml`.
3. **The embedder survives.** `src/rag/embedder.py` is live and unrelated to P4 — it powers the fridge (`src/monitor/fridge.py`), which chunks and retrieves per-topic research text by pgvector cosine similarity in the Exilus lane.
4. **The publish loop survives.** `record_post.py` / `enter_views.py` / `compute_percentiles.py` keep recording outcomes. Percentile labels remain useful as a plain performance record whether or not a model is ever fit to them.
5. **The eval harness survives.** `src/evals/harness.py`, `metrics.py`, and `groundedness_check.py` gate the pipeline that actually runs. Only the Blueprint-specific eval component goes.
6. **If prediction ever returns, it trains on posted renders** — our own clips and their percentile outcomes, with features drawn from what we control at generation time (script structure, register, beat count, reference binding). Not on a scraped third-party corpus.

## Consequences

- **The fallback commercial wedge is gone.** If the content experiment fails, there is no labelled-archive product to fall back on. That is accepted: the wedge was only viable while the corpus resembled the output, and the "sell predictions about TikTok virality" business was never started.
- **Portfolio breadth narrows on paper, not in substance.** The RAG story is now the fridge — chunking, BGE-M3 embeddings, pgvector cosine/HNSW retrieval, wired into a live loop — which is a stronger demonstration than a retrieval stack no caller invokes.
- **The archive on `D:\tiktok_archive` is untouched.** ~72k videos and their manifest stay on disk. This ADR deletes the code that processes them, not the data. Re-ingesting later means writing a new extractor against whatever the then-current product needs.
- **Test count drops.** The deleted modules take their tests with them.
- **Database tables outlive their models.** Dropping an ORM model does not drop its table, and existing Alembic revisions still create `blueprints`, `viral_videos`, and friends. Those migrations are left intact so `alembic upgrade head` still runs cleanly on a fresh clone; the tables are simply unused. A follow-up migration may drop them, deliberately and separately.
- **Docs that describe P4 as pending are now wrong** and are updated alongside this ADR: `CLAUDE.md` (roadmap, key directories, the dormant-by-design bullet) and the README component table.

## Rollback

Everything deleted here is recoverable from git history — this ADR names the commit that performs the deletion, so `git revert` or a targeted `git checkout <sha> -- <path>` restores any module. The tables and the raw archive both survive the deletion, so a revert restores a working lane rather than an empty shell. Reversing the *decision* is a new ADR, so the trail stays intact.

## Considered alternatives

**Keep the code, mark it dormant** — the status quo, rejected. Dormant-by-design was honest while the corpus and the product were the same shape. Once the product moved to POV renders, "dormant" became a label on code that no future version of this project would call. Carrying it costs test-suite time, lint/type baseline noise, and a standing invitation to misread the repo's actual architecture (which already happened: a stale "`src/rag/` is dormant" claim in `CLAUDE.md` survived the fridge landing and misled several audits of this codebase).

**Delete the code and the archive together** — rejected. The 72k-video archive cost real money to ingest and is inert on disk. Deleting code is reversible via git; deleting the archive is not.

**Keep the Blueprint retrieval stack for portfolio value** — rejected. Retrieval code that nothing calls demonstrates less than the fridge, which does the same work in a live path. Breadth claimed but unwired reads worse to a reviewer than a narrower, honest system.
