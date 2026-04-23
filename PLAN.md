# AI Content Generation Pipeline — Implementation Plan

> **Note:** This plan was rewritten on 2026-04-22 to overlay the AI Engineer roadmap onto the base pipeline. See also: `docs/superpowers/specs/2026-04-22-ai-engineer-roadmap.md` for the master roadmap document. If you're lost, open this file first. It tells you what phase you're on and what to do next.

---

## Context

Build a personal tool that monitors trending content across TikTok, Instagram, YouTube Shorts, and Twitter/X, analyzes what makes them viral, generates optimized prompts, and produces full content packages (video + script + captions + thumbnail + hashtags) using AI.

**Twist as of 2026-04-22:** the project is also a portfolio artifact for an AI Engineer role. Every phase adds a first-class AI Engineering skill (RAG, evals, ML training, agents, LoRA fine-tuning, observability) on top of the base pipeline. Output: a defensible interview project, not just an API wrapper.

---

## Tech Stack

### Base pipeline
| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.13+ | Best AI/ML ecosystem, all APIs have Python SDKs |
| Backend | FastAPI | Async-native, auto OpenAPI docs, clean for approval workflow API |
| Frontend (MVP) | Vite + React + TypeScript | Industry-standard SPA framework |
| Database (local) | SQLite via SQLAlchemy 2.0 + Alembic | Zero setup, swap to PostgreSQL later |
| Database (cloud) | RDS PostgreSQL with `pgvector` extension | Managed, supports vector search natively |
| Task Queue | RQ (Redis Queue) | Handles long-running video generation jobs |
| Config | Pydantic Settings + YAML | Secrets in `.env`, user settings in YAML |
| Package Mgr | uv | Fast, modern lockfile manager |
| Containerization | Docker + Docker Compose | Reproducible environments |
| Cloud | AWS (ECS Fargate, RDS, S3, ECR) | Managed containers |
| Future | Kubernetes (EKS) | Scaling path if SaaS |

### AI Engineering stack (added 2026-04-22)
| Domain | Choice | Used in phase |
|---|---|---|
| Observability | Langfuse | P0 onward (all LLM calls traced) |
| Structured output | `instructor` + Pydantic | P0 onward |
| Text embeddings | `sentence-transformers`, OpenAI `text-embedding-3-small` | P2 (RAG) |
| Multimodal embeddings | `open-clip-torch` | P2 (thumbnails) |
| Vector DB | `pgvector` extension on Postgres | P2 |
| Hybrid search | `rank-bm25` + BGE-reranker-v2-m3 | P2 |
| ML classical | `lightgbm`, `scikit-learn`, `pandas`, `numpy` | P4 (virality predictor) |
| ML deep | `torch`, `transformers` | P4 (multimodal predictor) |
| Fine-tuning | `peft`, `trl`, `datasets`, `accelerate` | P6 (LoRA) |
| Inference | `vllm` or HF `transformers` | P6 serving |
| Agents | LangGraph or raw function-calling | P5 |
| Safety | `presidio-analyzer` + moderation API | P3 |

---

## Architecture Overview

```
[Scrapers] → [Raw Content DB + Vector Index] → [ML Virality Predictor]
    → [User Approves Trend] → [RAG Retrieval] → [Prompt Engine + Model Router]
    → [User Approves Prompts] → [Agent Orchestrator → Providers (video/TTS/image/LLM)]
    → [Safety Guardrails] → [User Approves Content] → [Output Packager]
    → local files + S3 + metadata

Everywhere: Langfuse tracing. Everywhere: eval harness scores components against golden set.
```

**Key design principles:**
1. **Pluggable providers.** External services (video, TTS, LLM, image, embedder, reranker, ML predictor) implement abstract base classes. Swap via YAML.
2. **Eval-driven.** No AI component ships without a metric against the golden set.
3. **Observable.** Every LLM/provider call traced with cost + latency.
4. **Own dataset, own model.** Scraped data → labeled golden set → trained predictor → fine-tuned hook LLM. Differentiator.

---

## Project Structure

```
ai-content-generation/
├── pyproject.toml
├── alembic.ini
├── config/
│   ├── settings.yaml
│   ├── providers.yaml
│   ├── .env                   # gitignored
│   └── .env.example
├── src/
│   ├── main.py                # FastAPI entry
│   ├── config.py              # Pydantic Settings loader
│   ├── database.py            # SQLAlchemy engine + session
│   ├── models/                # ORM: trend, content, niche, viral_video, eval_run, prediction
│   ├── schemas/               # Pydantic request/response
│   ├── scrapers/              # base, youtube, tiktok, instagram, twitter, scheduler
│   ├── analysis/              # rule-based (legacy), feature extractors feeding ML
│   ├── observability/         # Langfuse wrapper, tracing decorators
│   ├── rag/                   # embedder, indexer, retriever, schemas
│   ├── evals/                 # harness, judges, metrics, golden loader
│   ├── ml/                    # features, train, predict, serve (virality predictor)
│   ├── agents/                # orchestrator, tools, prompts
│   ├── finetune/              # data_prep, train_lora, eval_finetune
│   ├── generation/            # prompt_engine, script_writer, safety
│   ├── providers/             # base, registry, video/, tts/, llm/, image/, embeddings/, reranker/
│   ├── pipeline/              # workflow state machine, approval gates
│   ├── output/                # packager, file_manager (local + S3)
│   └── api/                   # FastAPI routes: trends, content, providers, evals, dashboard
├── ui/                        # React + Vite + TS (unchanged from prior plan)
├── data/
│   ├── golden/                # Labeled eval set (jsonl)
│   ├── scraped/               # Raw scrape dumps (gitignored)
│   └── finetune/              # Curated hook dataset (gitignored)
├── notebooks/                 # EDA, experiments, eval analysis
├── output/                    # Generated content (gitignored)
├── infra/
│   ├── docker/                # Dockerfiles
│   ├── docker-compose.yml
│   ├── aws/                   # ECS task defs, IaC
│   ├── modal/                 # LoRA fine-tune job config
│   └── runpod/                # alt GPU config
├── docs/
│   ├── superpowers/specs/     # Master roadmap + per-phase specs
│   └── learnings/             # Per-phase learning notes
├── tests/
└── scripts/                   # Utility scripts
```

---

## Database Schema (Key Tables)

Base tables:
- **`niches`** — name, keywords, hashtag seeds, is_active
- **`raw_content_items`** — platform, content ID, views/likes/comments/shares, audio ID, hashtags, duration, format, URL, timestamps, transcript (indexed for dedup + time queries)
- **`detected_trends`** — trend type, confidence score, velocity score, supporting content IDs, status
- **`content_requests`** — linked trend, workflow state, prompts, script, caption, hashtags, duration, style
- **`generated_assets`** — linked content request, asset type, provider used, file path, cost
- **`provider_calls`** — every API call: provider, params, cost, duration, success/failure
- **`approval_events`** — every approval/rejection (ML training data)

AI-Eng tables (added in roadmap phases):
- **`viral_videos`** — enriched raw content with embeddings (pgvector column), indexed for retrieval (P2)
- **`golden_labels`** — manual labels: content_id, virality_class (viral/mid/flop), best_hook_text, annotator, notes (P1)
- **`eval_runs`** — timestamp, component, git_sha, metric_name, metric_value, dataset_version (P1)
- **`predictions`** — content_id, model_name, model_version, virality_score, features_hash (P4)
- **`retrieval_logs`** — query, retrieved_ids, scores, used_in_generation_id (P2-3)

---

## External Services

| Service | Purpose | Cost | Phase |
|---|---|---|---|
| YouTube Data API v3 | Scrape Shorts | Free (10K units/day) | P0 |
| Apify (TikTok / IG actors) | Scrape TikTok + Reels | ~$0.30-0.50/1K posts | P0 |
| Langfuse | LLM observability | Free tier sufficient | P0 |
| OpenAI API | `text-embedding-3-small`, LLM fallback | Cheap embeddings, metered LLM | P0, P2 |
| Anthropic API | Claude Haiku + Sonnet/Opus for model routing | Metered | P3 |
| Cohere Rerank (optional) | Retrieval rerank | Metered, or swap to local BGE | P2 |
| Modal or Runpod | A100 GPU for LoRA training | ~$2/hr, few hrs per run | P6 |
| Hugging Face Hub | Model weights (Qwen/Llama, BGE, CLIP) | Free | P2, P6 |
| Seedance / Kling / Runway | Video generation | Per-video | P3 |
| OpenAI TTS / ElevenLabs | Narration | Metered | P3 |
| DALL-E 3 | Thumbnails | Per-image | P3 |
| AWS ECR / ECS / RDS / S3 | Deploy | Mostly free tier | P7 |

---

## Development Phases

> Phases mirror `docs/superpowers/specs/2026-04-22-ai-engineer-roadmap.md`. This document is the **task list** — roadmap is the **rationale**. Open this when starting a work session. Check off steps. When a phase ends, write a learning note in `docs/learnings/`.

### Phase 0 — Foundation (Week 1)
_Goal: data flowing, observability scaffolded, structured-output discipline established BEFORE first LLM call._

#### Step 0.1 — Finish environment
- [ ] Run `uv sync` to install the AI-Eng deps added to `pyproject.toml`
- [ ] Verify: `uv run python -c "import langfuse, instructor, lightgbm, torch, transformers; print('ok')"`
- [ ] Create Langfuse cloud account (free). Add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` to `config/.env`

**Learn:** what observability actually gives you (traces, spans, cost/latency, eval linking). Watch: Langfuse 10-min tour.

#### Step 0.2 — Observability wrapper
- [ ] Create `src/observability/__init__.py`
- [ ] Create `src/observability/tracing.py` — Langfuse client singleton + a `@traced` decorator that wraps any function, logs args + result + latency + cost
- [ ] Write a "hello world" script: call Claude Haiku with `"say hi"`, see trace land in Langfuse dashboard

**Concepts:** decorators, context managers, spans vs traces, PII in traces (redact before logging).

#### Step 0.3 — Structured output discipline
- [ ] Add `src/schemas/llm.py` — Pydantic models for every LLM output shape you'll use: `TrendAnalysis`, `ScriptPackage`, `HookVariant`, `SafetyCheck`
- [ ] Create `src/providers/llm/anthropic_llm.py` that uses `instructor` to force schema-valid output. Every LLM call returns a validated Pydantic object, not raw text.

**Concepts:** schema-first prompting, retries on parse failure, why `instructor` beats regex on JSON.

#### Step 0.4 — Scraper scheduler hardening
- [ ] Finish `src/scrapers/scheduler.py` with APScheduler, run every 6h
- [ ] Run for 2-3 days. Target: 500+ videos in `raw_content_items`
- [ ] Sanity check: `select platform, count(*) from raw_content_items group by platform`

**Phase 0 done when:** Langfuse shows a trace, 500+ videos in DB, every LLM call in the codebase validates against a Pydantic schema.

---

### Phase 1 — Data & Evals (Weeks 2-3)
_Goal: a golden eval set + harness that scores any AI component. Gate for everything downstream._

#### Step 1.1 — Alembic migration for eval tables
- [ ] Create migration: `golden_labels`, `eval_runs` tables (fields per schema section above)
- [ ] Run `alembic upgrade head`

#### Step 1.2 — Label 100 videos
- [ ] Build a tiny CLI (`scripts/label.py`) that shows one video row at a time and prompts for: virality class, best hook text, notes
- [ ] Label 100 videos across niches. Save to `data/golden/labels.jsonl` + mirror into `golden_labels` table
- [ ] Document labeling methodology in `docs/learnings/2026-XX-labeling.md` (criteria for viral/mid/flop)

**Concepts:** inter-annotator agreement, labeler bias, why hand-labels matter more than ML tricks.

#### Step 1.3 — Eval harness
- [ ] Create `src/evals/harness.py` — pytest-style runner. Loads golden set, dispatches to registered scorers, writes results to `eval_runs`
- [ ] Create `src/evals/metrics.py` — AUC, precision@k, MRR, hit@k implementations
- [ ] Create `src/evals/judges.py` — LLM-as-judge prompts for script quality, using Claude Sonnet
- [ ] CLI entry: `uv run eval-harness --component=rule-based-scorer` outputs JSON report

#### Step 1.4 — Baseline scorer eval
- [ ] Implement a placeholder rule-based scorer in `src/analysis/` (engagement velocity heuristic)
- [ ] Run it through the harness. Record baseline AUC. This is the number ML has to beat in P4.
- [ ] Langfuse dashboard screenshot: cost + latency of LLM-judge calls

**Phase 1 done when:** `uv run eval-harness` produces a JSON report. Baseline AUC recorded. Golden set committed.

---

### Phase 2 — RAG Layer (Weeks 4-5)
_Goal: scraped archive = retrieval corpus. Future generation grounds in real viral examples._

#### Step 2.1 — pgvector setup
- [ ] Switch local DB to Postgres via Docker Compose (SQLite won't cut it for pgvector)
- [ ] Alembic migration: enable `pgvector` extension, add `viral_videos` table with `embedding vector(1024)` column (BGE dimension)
- [ ] Update `src/database.py` to accept Postgres URL

#### Step 2.2 — Embedder
- [ ] Create `src/rag/embedder.py` — abstract `TextEmbedder` + concrete `BGEEmbedder` (local, via sentence-transformers) and `OpenAIEmbedder` (API)
- [ ] Register in `providers.yaml` with active embedder configurable
- [ ] Multimodal: `ThumbnailEmbedder` using OpenCLIP

#### Step 2.3 — Indexer
- [ ] Create `src/rag/indexer.py` — batch job that reads unindexed `raw_content_items`, embeds title+transcript+hashtags, writes to `viral_videos`
- [ ] Run once over full scrape. Verify DB row counts match.

#### Step 2.4 — Retriever
- [ ] Create `src/rag/retriever.py` — hybrid search: BM25 over titles/transcripts (via `rank-bm25`) + vector cosine over pgvector + BGE-reranker-v2 rerank
- [ ] Pydantic schemas in `src/rag/schemas.py`: `RetrievalQuery`, `RetrievalHit`, `RetrievalResponse`

#### Step 2.5 — Retrieval eval
- [ ] Build 30 held-out query→expected-hit pairs in the golden set
- [ ] Run retriever through harness. Target: hit@5 > 0.7, MRR > 0.5
- [ ] Ablation: vector-only vs hybrid vs hybrid+rerank. Write findings in learning note.

**Phase 2 done when:** hybrid retriever beats vector-only on hit@5 in eval harness. 30 held-out retrieval queries committed.

---

### Phase 3 — Generation with RAG (Weeks 6-7)
_Goal: replace stub generation with RAG-grounded, structured, routed, guardrailed script generator._

#### Step 3.1 — Script writer
- [ ] Create `src/generation/script_writer.py` — takes a `RetrievalResponse` + niche + target duration, produces a validated `ScriptPackage` via `instructor`
- [ ] Few-shot prompt template in Jinja2: pulls top-K retrieved viral scripts as examples

#### Step 3.2 — Model routing
- [ ] Create `src/providers/llm/router.py` — task→model mapping in `providers.yaml`
- [ ] Routes: `tagging` → Haiku, `script` → Sonnet, `hook` → Opus (until fine-tune replaces in P6)
- [ ] All routed calls traced in Langfuse with routing decision logged

#### Step 3.3 — Safety guardrails
- [ ] Create `src/generation/safety.py` — pre-publish check: PII via Presidio, content safety via Anthropic moderation or simple profanity filter
- [ ] Return structured `SafetyCheck` result. Block or flag per severity.

#### Step 3.4 — Generation eval
- [ ] Add generation scorer to harness: LLM-judge compares (RAG-script vs naked-prompt-script)
- [ ] Target: judge prefers RAG version on ≥70% of queries
- [ ] Log cost per script package in `provider_calls`

**Phase 3 done when:** script writer produces validated `ScriptPackage` via RAG + routing + safety. Eval harness shows RAG wins.

---

### Phase 4 — ML Virality Predictor (Weeks 8-10)
_Goal: replace rule-based scoring with trained classifier. Two models head-to-head on golden set._

#### Step 4.1 — Feature engineering
- [ ] Create `src/ml/features.py` — extracts: engagement velocity, hashtag freq, post hour, duration, creator baseline, title embedding (PCA to 32 dims), thumbnail CLIP embedding (PCA)
- [ ] Export to pandas DataFrame, save to `data/scraped/features.parquet`

#### Step 4.2 — LightGBM baseline
- [ ] Create `src/ml/train.py` — LightGBM binary classifier (viral vs not)
- [ ] Stratified train/val/test split (60/20/20)
- [ ] Track: AUC, precision@10, calibration plot (reliability diagram)
- [ ] Save model to `data/models/lightgbm_v1.pkl`

#### Step 4.3 — Multimodal neural model
- [ ] `src/ml/train.py` (neural path): MLP taking [CLIP-thumbnail || text-embed || numeric-features] → virality score
- [ ] Train with `torch`. Track same metrics.

#### Step 4.4 — Predictor service
- [ ] Create `src/ml/predict.py` — loads model, exposes `predict(content_id) -> {score, version, features_hash}`
- [ ] FastAPI endpoint `POST /predict/virality` in `src/api/`
- [ ] Writes predictions to `predictions` table

#### Step 4.5 — Head-to-head eval
- [ ] Register both models with harness. Target: AUC ≥ 0.75, predictor beats rule-based on precision@10
- [ ] Feature flag in `settings.yaml`: `virality_scorer: ml | rule-based`
- [ ] Document findings + calibration plot in learning note

**Phase 4 done when:** trained predictor replaces rule-based scorer behind flag. Calibration plot committed.

---

### Phase 5 — Agent Orchestrator (Week 11)
_Goal: LLM-driven pipeline routing. Approval flow becomes a tool-calling agent._

#### Step 5.1 — Tool definitions
- [ ] Create `src/agents/tools.py` — wrap existing functions as agent tools with typed signatures + docstrings: `scrape_platform`, `predict_virality`, `retrieve_similar`, `generate_script`, `generate_video`, `generate_thumbnail`, `request_human_approval`
- [ ] Each tool auto-logged in Langfuse

#### Step 5.2 — Orchestrator agent
- [ ] Create `src/agents/orchestrator.py` — LangGraph state machine OR raw function-calling loop. Planner prompt in `src/agents/prompts.py`
- [ ] States: idle → retrieving → predicting → generating → awaiting_approval → packaging → done / failed
- [ ] Retry + fallback logic in planner: on rate-limit, escalate to cheaper provider

#### Step 5.3 — End-to-end agent run
- [ ] CLI: `uv run agent --topic=cooking`
- [ ] Agent independently decides: scrape? retrieve? predict? generate? Human-approves at gates.
- [ ] Trace the full run in Langfuse, count tool calls, cost

**Phase 5 done when:** agent runs end-to-end with 0 code-level branching — all routing by LLM. Trace screenshotable.

---

### Phase 6 — LoRA Fine-Tune (Weeks 12-14)
_Goal: fine-tune a small open LLM on viral-hook data. Differentiator bullet._

#### Step 6.1 — Dataset curation
- [ ] Create `src/finetune/data_prep.py` — pull top-engagement videos from `raw_content_items`, extract (context, viral_hook) pairs
- [ ] Clean: dedup, profanity filter, length filter. Target: 2-5k pairs.
- [ ] Save as `data/finetune/hooks.jsonl` in conversational format (messages[]).

#### Step 6.2 — LoRA training
- [ ] Create `src/finetune/train_lora.py` — uses `trl` SFTTrainer on Qwen-2.5-7B-Instruct (or Llama-3.1-8B)
- [ ] LoRA config: r=16, alpha=32, target attn+mlp
- [ ] Run on Modal or Runpod A100 (decide per `infra/modal/` or `infra/runpod/` config)
- [ ] Push adapter to Hugging Face Hub (private repo)

#### Step 6.3 — Fine-tune eval
- [ ] Create `src/finetune/eval_finetune.py` — LLM-judge comparing: (a) LoRA Qwen hook, (b) base Qwen hook, (c) GPT-4o hook
- [ ] Pairwise preference, win rates on golden hook set
- [ ] Small human eval: n=30, self + friends

#### Step 6.4 — Deploy fine-tuned model
- [ ] Serve via vLLM or HF transformers + FastAPI
- [ ] Register in `providers.yaml` as `llm.qwen_hook_ft`
- [ ] Router sends `hook` task to fine-tuned model

**Phase 6 done when:** LoRA beats base Qwen on hook-judge. Deployed and routed. Training run reproducible from one script.

---

### Phase 7 — Polish & Deploy (Week 15+)
_Goal: ship it. Case study README. Live demo on AWS._

#### Step 7.1 — Docker containerization
- [ ] Dockerfiles: `api`, `worker`, `ui`. Multi-stage builds.
- [ ] `docker-compose.yml` with Postgres (pgvector), Redis, API, worker, UI
- [ ] `.dockerignore` correct

#### Step 7.2 — AWS deploy
- [ ] ECR repos, push images
- [ ] RDS Postgres with `pgvector` extension enabled
- [ ] ECS Fargate services for api + worker + ui, ALB routing
- [ ] S3 for generated content
- [ ] Secrets via AWS Secrets Manager
- [ ] CloudWatch logs wired

#### Step 7.3 — Dashboard + case study
- [ ] Dashboard page (in React or Streamlit): prediction scores, retrieval hits, eval scores over time, cost/package, fine-tune vs base win rate
- [ ] Rewrite `README.md` as case study: problem, dataset stats, architecture diagram, eval tables, fine-tune results, honest limitations, lessons learned
- [ ] Record demo video: end-to-end run narrated

**Phase 7 done when:** stranger reads README and knows what was built + why + which metrics back it. Demo runs live on AWS.

---

## Cross-Phase Standards

- **Every LLM call** wraps through `@traced` decorator.
- **Every AI component** registers an eval in the harness before merge.
- **Every new directory** gets a short `README.md`.
- **Every phase** ends with a learning note in `docs/learnings/YYYY-MM-DD-phaseN-topic.md`.
- **Cost ceiling:** aim for under $150 total external API spend across P0-P5. P6 fine-tune GPU separate (~$20-50/run).

---

## Pair-Programming Model

See `CLAUDE.md` section "Important: Learning Project — Pair-Programming Model" for tiers of help, who writes what, anti-drift rules. Short version: AI teaches concepts + writes boilerplate, user writes business logic, AI reviews.

---

## Key Technical Challenges

| Challenge | Solution |
|---|---|
| Video gen APIs are slow (30s-5min) | Async tasks with timeout, retry, fallback provider |
| YouTube API quota (10K/day) | Batch per niche, cache, Apify fallback |
| Apify scrapers break | BaseScraper interface, skip broken scrapers |
| Rule-based detection has false positives | Replaced by ML in P4; approval logs = training data |
| Provider landscape changes | Pluggable registry: new provider = 1 file + YAML entry |
| AI content feels generic | RAG grounds in real viral examples; fine-tuned hook model beats generic LLM |
| SQLite → Postgres migration | SQLAlchemy abstracts; Alembic works across both; Postgres needed for pgvector anyway |
| Secrets in cloud | AWS Secrets Manager, never in images |
| ECS costs creep | Fargate Spot for workers, right-size defs, stop dev when idle |
| Eval drift / regressions | Harness runs in CI on PRs; fail on AUC drop >0.02 |
| Fine-tune GPU cost | Modal serverless (scale-to-zero) or Runpod spot |

---

## MVP Scope (Revised)

- **Platforms:** YouTube + TikTok (IG lower priority)
- **Trend detection:** ML virality predictor (P4) behind flag, rule-based as fallback
- **Retrieval:** hybrid RAG (P2)
- **LLM:** Claude Haiku + Sonnet routed; fine-tuned Qwen for hooks (P6)
- **Embeddings:** BGE local + OpenAI
- **Video gen:** 1 provider
- **TTS:** OpenAI TTS
- **Thumbnails:** DALL-E 3
- **Agent:** LangGraph or raw orchestrator (P5)
- **Workflow:** 3-step approval in React dashboard
- **Output:** local files + S3
- **Database:** Postgres + pgvector (local Docker → RDS cloud)
- **Hosting:** local → Docker Compose → ECS Fargate
- **Observability:** Langfuse throughout

---

## Verification Plan

1. **Scrapers:** data appears in `raw_content_items` with correct schema
2. **Observability:** every LLM call visible in Langfuse with cost + latency
3. **Structured output:** every LLM return validates against a Pydantic schema
4. **Golden set:** 100 labeled videos committed, labeling methodology documented
5. **Eval harness:** `uv run eval-harness` produces JSON report; CI fails on metric drop
6. **Retrieval:** hit@5 > 0.7 on held-out queries
7. **Generation:** LLM-judge prefers RAG script ≥70% of the time
8. **ML predictor:** AUC ≥ 0.75 on test set; calibration plot committed
9. **Agent:** end-to-end run with 0 code-level branching; Langfuse trace captures all tool calls
10. **Fine-tune:** LoRA beats base on hook-judge; reproducible from one script
11. **Deploy:** docker compose up works local; ECS Fargate run works cloud
12. **Case study:** README has architecture diagram, dataset stats, eval tables, lessons
