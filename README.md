# AI Content Generation Pipeline

An end-to-end system that studies what makes short-form video work, then generates new video concepts grounded in that evidence — scrape → structured analysis → retrieval → generation → render → evaluate.

Built as a personal project to find out how far you can push LLM application engineering when nobody hands you a framework: typed contracts between every stage, cost governance before any paid call, and an evaluation harness that scores each change instead of trusting vibes.

## Tech Stack

**Backend** Python · FastAPI · SQLAlchemy · Alembic · PostgreSQL + pgvector
**LLM** LangGraph · Pydantic · Anthropic API · OpenRouter
**Retrieval** BGE-M3 embeddings · HNSW indexing · reranking
**Infra** Docker Compose · Langfuse tracing

## What It Does

- **Scrapes** short-form video from TikTok, YouTube, and Instagram on a schedule (`src/scrapers/`).
- **Extracts a Blueprint** from each video — a versioned schema of its structure (hook type, pacing, loop quality, niche) that is both observable from a finished video and actionable by the generator (`src/blueprints/`).
- **Indexes** the corpus into a pgvector store with BGE-M3 embeddings, HNSW indexes, and a reranking stage, so generation can retrieve stylistically similar neighbours (`src/rag/`).
- **Monitors** trending events and names the *unmet audience desire* behind the reaction, then pitches distinct creative angles against it (`src/monitor/`).
- **Writes and renders** a single-shot video package — opening keyframe, motion prompt, audio line, caption — in the routed video model's own dialect, then runs the render jobs and verifies the output (`src/generation/`).
- **Evaluates** everything: LLM-as-judge scoring, groundedness checks, RAG retrieval metrics, and self-agreement runs, all keyed to a git SHA so results stay comparable across changes (`src/evals/`).

## Engineering Notes

The parts I'd actually talk about in an interview:

- **Typed contracts between stages.** Every hand-off is a Pydantic schema (`src/schemas/`, `src/models/`), so a malformed LLM response fails at the boundary it was produced at, not three stages downstream.
- **Config-driven provider routing.** Models, pricing, and per-model prompt dialects live in YAML (`config/providers.yaml`, `config/render_rules.yaml`), not in code — adding a provider is a config change.
- **Cost governance.** Preflight pricing states the credit cost before any paid call, budget ceilings cap a run, and `--dry-run` returns the estimate without spending.
- **Validate → repair → escalate.** Structured outputs that fail validation get one repair attempt against the same model before escalating to a stronger one, rather than retrying blindly.
- **Evaluation as a first-class stage.** Cross-model judges and groundedness gates sit between generation and acceptance; the harness records scores per git SHA so a regression is visible.
- **74 test modules faking every paid external API,** so the full suite runs offline and costs nothing.

## Running It

```bash
git clone https://github.com/Zifan12/ai-content-generation.git
cd ai-content-generation

cp config/.env.example .env      # add your API keys
docker compose -f infra/docker-compose.yml up -d   # Postgres + pgvector
uv sync
uv run alembic upgrade head      # 15 migrations

uv run pytest                    # full suite, no network, no spend
```

Pipeline stages run as individual scripts — for example:

```bash
uv run python scripts/run_scrape.py
uv run python scripts/extract_blueprints.py
uv run python scripts/pitch_angles.py
```

## Project Structure

```
src/
  scrapers/      TikTok / YouTube / Instagram ingestion + scheduling
  blueprints/    structured extraction of video mechanics
  rag/           embedding, indexing, retrieval, reranking
  monitor/       trend scanning, gap analysis, angle pitching
  generation/    content writer, render adapters, executor
  evals/         judges, harness, metrics, groundedness checks
  providers/     LLM / image / video / TTS provider adapters
  observability/ Langfuse tracing
  api/           FastAPI app
config/          provider, pricing, and render-rule YAML
alembic/         15 schema migrations
tests/           74 test modules, all external APIs faked
```

## What I'd Improve

- The trend monitor depends on scraped reaction text; that is the most fragile input in the system and deserves a quality gate of its own.
- The writer eval rubric is currently parked behind a paradigm change and needs rebuilding against the single-shot format.
- Provider routing is config-driven but still routes to one default video model; a premise-classifying router is designed, not built.

---

Built by [Zifan Li](https://github.com/Zifan12) · [Portfolio](https://zifan-portfolio.vercel.app) · [LinkedIn](https://www.linkedin.com/in/li-zifan)
