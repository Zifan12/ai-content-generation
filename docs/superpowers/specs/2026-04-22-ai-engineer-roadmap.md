# AI Engineer Roadmap — AI Content Generation Pipeline

**Date:** 2026-04-22
**Owner:** Zifan
**Status:** Draft — master overlay on existing PLAN.md
**Goal:** Transform existing content-gen pipeline into a portfolio-grade AI Engineer project that signals RAG, evals, ML, agents, fine-tuning, and observability skills.

---

## Context

Existing project (see `PLAN.md`, `CLAUDE.md`, `SPECS.md`) is an API-orchestration pipeline: scrape trending content → rule-based trend scoring → LLM-generated scripts → provider calls for video/TTS/image → approval gates → output package.

Current state (2026-04-22):
- Scrapers: YouTube + Instagram working (~400 LOC).
- Models: `trend`, `niche` only.
- Analysis, generation, providers, pipeline, api: empty stubs.
- Config, alembic, tests scaffolding in place.

Problem: current design reads as "API wrapper." Recruiters scanning for AI Engineer signal will not see RAG, evals, training, fine-tuning, or agentic work. This roadmap adds those as first-class pillars, baked into the architecture rather than bolted on.

---

## Guiding Principles

1. **Eval-driven.** Every AI component is measured against a golden dataset. No feature ships without a metric.
2. **Observability from day one.** Every LLM/provider call is traced in Langfuse with cost and latency.
3. **Own data, own model.** Scrape real data, label a golden set, train own classifier, fine-tune own LLM on that data. Differentiator = dataset + trained models, not API calls.
4. **Learning-first.** User implements code. AI teaches concepts, provides skeletons, reviews. Pair-programming model documented in `CLAUDE.md`.
5. **YAGNI with a ceiling.** Portfolio project — enough depth to defend in interviews, not production-complete.

---

## Tech Stack Additions

| Domain | Addition | Purpose |
|---|---|---|
| Observability | `langfuse` | Trace LLM calls, cost, latency, eval scores |
| Structured output | `instructor` + Pydantic | Force schema-valid LLM outputs |
| Embeddings | `sentence-transformers`, OpenAI `text-embedding-3-small` | Text embeddings for retrieval |
| Multimodal | `open-clip-torch` | Thumbnail embeddings |
| Vector DB | `pgvector` extension on Postgres | Stays within existing DB choice |
| Hybrid search | `rank-bm25` | Lexical side of hybrid retrieval |
| Reranker | BGE-reranker-v2-m3 (local) or Cohere Rerank API | Retrieval quality boost |
| ML | `lightgbm`, `scikit-learn` | Virality predictor baseline |
| Neural | `torch`, `transformers` | Multimodal predictor, inference |
| Fine-tuning | `peft`, `trl`, `datasets`, `accelerate` | LoRA on Qwen/Llama |
| Serving | `vllm` (optional) | Serve fine-tuned model |
| Agents | LangGraph or raw function-calling | Orchestrator agent |
| Safety | `presidio-analyzer` or simple regex + moderation API | PII and content safety |
| Notebooks | `jupyter`, `matplotlib`, `seaborn` | EDA and model experiments |

All added to `pyproject.toml` upfront to avoid lockfile churn later.

---

## Target Directory Structure

New directories (additions to `src/`, `data/`, `infra/`, `notebooks/`, `docs/`):

```
src/
├── observability/      # Langfuse wrapper, tracing decorators, cost/latency logging
├── rag/
│   ├── embedder.py     # Text + thumbnail embedding service
│   ├── indexer.py      # Populate pgvector table from scraped content
│   ├── retriever.py    # Hybrid search (BM25 + vector) + rerank
│   └── schemas.py      # Retrieval request/response models
├── evals/
│   ├── harness.py      # pytest-style runner, loads golden set, runs scorers
│   ├── judges.py       # LLM-as-judge prompts + scorers
│   ├── metrics.py      # AUC, hit@k, BLEU-style, calibration
│   └── golden.py       # Golden set loader/validator
├── ml/
│   ├── features.py     # Feature engineering from scraped videos
│   ├── train.py        # LightGBM + neural training scripts
│   ├── predict.py      # Inference service, loaded into pipeline
│   └── serve.py        # FastAPI endpoint for predictions
├── agents/
│   ├── orchestrator.py # Planner agent, decides pipeline flow
│   ├── tools.py        # Tool definitions wrapping scrapers/predictors/generators
│   └── prompts.py      # System prompts for agent
├── finetune/
│   ├── data_prep.py    # Curate (context → viral hook) pairs
│   ├── train_lora.py   # LoRA training script (runs on Modal/Runpod)
│   └── eval_finetune.py# Compare fine-tune vs base vs GPT-4o on golden set

data/
├── golden/             # Labeled eval set (csv or jsonl)
├── scraped/            # Raw scrape dumps (gitignored)
└── finetune/           # Curated hook dataset (gitignored)

notebooks/              # EDA, model experiments, eval result analysis

infra/
├── modal/              # Fine-tune job config (if Modal used)
└── runpod/             # Alternative cloud GPU config

docs/
├── superpowers/specs/  # Phase specs (this file lives here)
└── learnings/          # Per-phase learning notes / study logs
```

Existing scrapers, models, config, alembic are preserved and extended, not replaced.

---

## 7-Phase Roadmap

### Phase 0 — Foundation (week 1)
Finish scrape→DB loop with real data flowing. Scaffold observability and structured-output discipline before any LLM call is written.
- Scraper scheduling (APScheduler) runs and persists.
- Pydantic schemas for all LLM I/O envelopes.
- Langfuse account + tracing decorator wrapping any future LLM call.
- `pyproject.toml` updated with full AI-Eng stack.
- `CLAUDE.md` updated with pair-programming working model.

**Success metric:** 500+ videos scraped and stored. Langfuse receives a "hello world" trace.

### Phase 1 — Data & Evals (week 2-3)
Build the golden eval set and the harness that scores any AI component against it. Everything downstream plugs into this harness.
- Hand-label 100 scraped videos: viral / mid / flop, plus best-hook annotation.
- Eval harness runs scorers, reports metrics, writes to `eval_runs` table.
- LLM-as-judge prompts for script quality.
- Langfuse dashboards: cost, latency, eval scores.

**Success metric:** Can run `uv run evals harness` and get JSON report of metric deltas vs last run. Regressions fail CI.

### Phase 2 — RAG Layer (week 4-5)
Turn the scraped archive into a retrieval corpus. Every later generation prompt pulls grounded examples.
- `pgvector` extension, migration, `viral_videos` table with embedding column.
- Text embeddings (titles + transcripts + hashtags + metadata).
- CLIP thumbnail embeddings.
- Hybrid retrieval: BM25 + vector + BGE reranker.
- Retrieval quality evals: hit@k, MRR on held-out queries.

**Success metric:** "Find 5 similar viral cooking Shorts" returns grounded hits. Hit@5 > 0.7 on golden queries.

### Phase 3 — Generation with RAG (week 6-7)
Script generator uses retrieval + structured output + model routing. Replaces stub generation in existing `src/generation/`.
- Script writer: retrieves top-K viral scripts, few-shot prompts, outputs `ScriptPackage` Pydantic schema via `instructor`.
- Model routing: Haiku for tagging/classification, Sonnet/Opus for creative.
- Guardrails: content safety + PII scrub pre-save.
- All calls traced and eval'd against golden set.

**Success metric:** LLM-judge prefers RAG scripts over naked-prompt scripts on ≥70% of golden queries. Cost/script logged.

### Phase 4 — ML Virality Predictor (week 8-10)
Replace rule-based trend scoring with a trained classifier. Two models, compared head-to-head on golden set.
- Feature engineering: engagement velocity, hashtag freq, post hour, duration, creator baseline, title embedding PCA.
- LightGBM baseline on labeled golden set + weak labels from engagement thresholds.
- Multimodal neural: CLIP thumbnail + text embed + numeric features → MLP.
- FastAPI endpoint, both models pluggable via `providers.yaml`-style config.
- Both models run through eval harness.

**Success metric:** AUC ≥ 0.75 on test split. Predictor replaces rule-based scorer behind feature flag. Eval harness shows ML wins on precision@10.

### Phase 5 — Agent Orchestrator (week 11)
Formalize the approval pipeline into a tool-calling agent. Agent decides which scraper to invoke, when to retry, which provider to pick under failure.
- Tools: `scrape_*`, `predict_virality`, `retrieve_similar`, `generate_script`, `generate_video`, etc.
- Planner prompt + ReAct loop (LangGraph or raw function calling).
- Tracing: every tool call in Langfuse with args and outputs.
- Fallback logic: retry with cheaper provider on rate limit.

**Success metric:** End-to-end run from "topic=cooking" to generated package via agent, with 0 code-level branching logic — all routing is LLM-driven.

### Phase 6 — LoRA Fine-Tune (week 12-14)
Fine-tune a small open LLM on viral-hook data you scraped. The differentiator bullet.
- Data prep: curate 2-5k (video context → viral opening hook) pairs from scraped data.
- LoRA config on Qwen-2.5-7B-Instruct (or Llama-3.1-8B). Train on Modal or Runpod A100.
- Eval: LoRA hook vs base Qwen hook vs GPT-4o hook on golden set. LLM-judge + a small human eval (self + friends, n≥30).
- Deploy: vLLM endpoint or HF transformers served via FastAPI.
- Router sends "hook generation" subtask to fine-tuned model.

**Success metric:** Fine-tune beats base Qwen on hook-quality judge. Competitive with GPT-4o at a fraction of cost. Training run reproducible via single script.

### Phase 7 — Polish & Deploy (week 15+)
Ship it, write the case study.
- Docker Compose → ECS Fargate deploy (per existing PLAN.md).
- Dashboard (Streamlit or React page): virality prediction, retrieval hits, eval scores, cost/package, fine-tune vs base.
- README rewritten as case study: dataset stats, architecture diagram, eval tables, lessons, honest limitations.
- Demo video: end-to-end run narrated.

**Success metric:** Stranger can read README and know exactly what was built, why, and what metrics back it. Demo runs live on AWS.

---

## Cross-Phase Standards

- **Every new LLM call** wrapped in Langfuse tracing decorator.
- **Every new AI component** must have a corresponding eval entry before being merged.
- **Every new directory** gets a short `README.md` explaining purpose + key files.
- **Every phase** produces a learning note in `docs/learnings/` (concepts, pitfalls, resources).
- **Cost ceiling per phase** tracked — aim under $150 total external API spend across all phases excluding fine-tune compute.

---

## What This Roadmap Does NOT Do

- Replace `PLAN.md`. That document still owns product/UX/deployment spec. This is the AI-skills overlay.
- Lock implementation details. Per-phase specs (written just-in-time) detail file-level design when that phase begins.
- Prescribe exact model versions. By Phase 6 (month 3+), better small models will exist — revisit then.

---

## Success Definition (Interview-Ready)

Project is "done enough" for AI Engineer portfolio when:

1. Public repo has README case study with architecture diagram + eval tables.
2. Live demo reachable on AWS.
3. Six bullets defensible in 45-min interview:
   - Dataset: scraped, stats, labeling methodology.
   - Evals: golden set, judges, harness, CI gate.
   - RAG: pgvector, hybrid search, reranker, hit@k numbers.
   - ML predictor: features, models, AUC, calibration plot.
   - Agent: tool list, planner prompt, failure modes handled.
   - Fine-tune: dataset curation, LoRA config, head-to-head eval.
4. Langfuse dashboard screenshot-able for interview.
5. At least one "I was wrong about X" story per major component — shows iteration.

---

## Next Actions

1. Update `CLAUDE.md` with pair-programming working model section.
2. Update `pyproject.toml` with AI-Eng deps.
3. Begin Phase 0. Write `2026-04-29-phase-0-foundation-spec.md` when Phase 1 start approaches.
