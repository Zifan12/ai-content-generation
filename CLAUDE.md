# AI Content Generation Pipeline

## Project Overview
Personal tool that scrapes trending content from TikTok, Instagram, YouTube Shorts, and Twitter/X, analyzes virality patterns, and generates full content packages (video + script + captions + thumbnail + hashtags) using AI. May evolve into SaaS.

## Important: Learning Project — Pair-Programming Model

The user is building this project to learn AI Engineering. Default mode is teach-first, not do-for-them. However, pure solo with no help is unrealistic — the model below balances learning and progress.

### Tier of help (apply in this order)
1. **Concept first** — before any code is written for a new feature, explain what/why/how in plain terms. Name the pattern. Point at resources if useful.
2. **Skeleton / pseudocode** — give file structure, function signatures, docstrings describing intent. User fills logic.
3. **Stuck? Diagnose, don't solve** — point at the bug, explain the trap, describe the fix. User types the fix.
4. **Write code only when** — (a) user explicitly asks ("just write it"), or (b) scaffolding/boilerplate that teaches little (migrations, config files, library call-site boilerplate, dependency lists).

### Who writes what
- **User writes:** business logic, glue code, anything involving design decisions, anything non-trivial.
- **AI writes:** Alembic migrations, YAML configs, `pyproject.toml` edits, test scaffolding, library-call boilerplate (HuggingFace loader calls, Langfuse decorators), one-off scripts for data prep.
- **Pair:** complex algorithms, ML training loops, retrieval logic, eval harnesses. AI sketches, user implements, AI reviews.

### Checkpoint rule
Before each new file, AI states: what this file does, why it exists, its interface (class/function signatures + types), and where it plugs in. User implements. Then AI reviews.

### Anti-drift rules
- If AI has written implementation code for 2 files in a row without user typing any, STOP and ask: "Are you still learning, or do you want me to keep drafting?"
- If user asks "can you just write X," comply but explain what's going on at a conceptual level after.
- User may say "full code, no teaching" to explicitly override into write-for-me mode for a specific task.

### AI Engineering roadmap
See `docs/superpowers/specs/2026-04-22-ai-engineer-roadmap.md` for the 7-phase AI-skills overlay (RAG, evals, ML predictor, agents, LoRA fine-tune, observability). That document is the source of truth for what additional AI components are being added beyond the base pipeline in `PLAN.md`.

## Tech Stack
  - **Language**: Python 3.12+
  - **Backend**: FastAPI (async)
  - **Frontend**: React (Vite + TypeScript)
  - **Database**: SQLite via SQLAlchemy 2.0 + Alembic (local), RDS PostgreSQL (cloud)
  - **Task Queue**: RQ (Redis Queue)
  - **Config**: Pydantic Settings + YAML files
  - **Package Manager**: uv
  - **HTTP Client**: httpx (async)
  - **Templates**: Jinja2
- **Containerization**: Docker + Docker Compose
- **Cloud**: AWS (ECS Fargate, RDS, S3, ECR)
- **Future**: Kubernetes (EKS) as scaling path

## Architecture
- Pluggable provider system (Strategy pattern) — all external services (video gen, TTS, LLM, image gen) implement abstract base classes
- Providers configured via `config/providers.yaml` — swapping = YAML edit, no code change
- 3-step approval workflow: approve trend → approve prompts → approve generated content
- Rule-based trend detection (Phase 1-3), ML prediction (Phase 5)
- Local dev → Docker Compose → AWS ECS Fargate deployment path
- Kubernetes (EKS) as future scaling option

## Key Directories
- `src/scrapers/` — platform scrapers (YouTube API, Apify for TikTok/IG)
- `src/analysis/` — trend detection and engagement scoring
- `src/providers/` — pluggable external service wrappers (video, TTS, LLM, image)
- `src/generation/` — prompt engine, script writer, orchestrator
- `src/pipeline/` — workflow state machine and approval gates
- `src/models/` — SQLAlchemy ORM models
- `src/schemas/` — Pydantic request/response schemas
- `ui/` — React dashboard (Vite + TypeScript)
- `config/` — YAML settings and .env secrets
- `output/` — generated content (gitignored)
- `infra/` — Dockerfiles, docker-compose, AWS task definitions, IaC

## Conventions
- Async-first: use `async/await` for all I/O operations
- All providers must implement abstract base classes from `src/providers/base.py`
- New providers = 1 Python file + 1 YAML entry in `config/providers.yaml`
- Database migrations via Alembic (never modify schema without a migration)
- Secrets in `config/.env`, user settings in `config/settings.yaml`
- Generated content saved to `output/YYYY-MM-DD/{content_id}/`

## Workflow Orchestration

### 1. Plan Node Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One tack per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- DO NOT apply this section — see "Learning Project" above
- Instead: explain what's wrong and why, let the user fix it

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimat Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
- When you ship a feature and it doesn't work, log it in bugs.md with the error and your attempted fix. When fixed, update the entry with what actually solved it.
- Before implementing any feature, explain your plan and wait for confirmation
- Never implement features I haven't explicitly requested
- WHEN working on UI/design, reference design-rules.md
- WHEN working on optimization, reference optimization-rules.md
