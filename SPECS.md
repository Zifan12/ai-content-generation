# SPECS - AI Content Generation Pipeline

## 1. Problem
Creators need a repeatable way to find viral patterns and turn them into publishable short-form content quickly.

## 2. Goal
Create an end-to-end system that ingests trends, analyzes them, and generates complete content packages with approval gates.

## 3. MVP Success Criteria
- Pull trend data from at least one platform (YouTube Shorts) and store it.
- Run rule-based trend detection and produce ranked trend candidates.
- Generate one complete content package from an approved trend.
- Save outputs to `output/YYYY-MM-DD/{content_id}/`.
- Complete the flow with explicit approval gates.

## 4. Non-Goals (Initial MVP)
- No autonomous posting to social platforms.
- No full multi-tenant SaaS architecture.
- No advanced ML predictor until enough historical data exists.

## 5. Current Technical Decisions
- Language: Python 3.12+
- API backend: FastAPI (async)
- UI: React (Vite + TypeScript) in `ui/`
- DB: SQLite local, PostgreSQL later
- ORM/migrations: SQLAlchemy 2.0 + Alembic
- Background jobs: RQ + Redis
- Config: Pydantic Settings + YAML
- External calls: `httpx` async client
- Packaging/tooling: `uv`, Docker, Docker Compose

## 6. Architecture (High-Level)
1. Scrapers ingest platform content.
2. Data is normalized and persisted.
3. Analysis module scores and detects trends.
4. User approves a trend.
5. Generation module creates prompts/assets through providers.
6. User approves prompts and final generated content.
7. Output packager writes assets and metadata.

## 7. Core Components
- `src/scrapers/`: ingestion per platform
- `src/analysis/`: scoring and trend detection
- `src/providers/`: pluggable provider interfaces/adapters
- `src/generation/`: prompt/script/orchestration
- `src/pipeline/`: workflow + approvals
- `src/models/`: persistence models
- `src/schemas/`: API contracts

## 8. Data Model (Initial)
- `niches`
- `raw_content_items`
- `detected_trends`
- `content_requests`
- `generated_assets`
- `provider_calls`
- `approval_events`

## 9. Implementation Order
1. Finalize DB schema and migrations.
2. Complete and verify YouTube scraper ingestion.
3. Implement trend scoring/detection rules.
4. Implement provider base classes and one mock provider path.
5. Implement prompt engine and orchestration path.
6. Wire approval flow end-to-end.
7. Build React dashboard (trends, generation, review pages).

## 10. Testing Strategy
- Unit tests for scraper normalization, trend scoring, and provider registry.
- Integration test for one vertical slice (scrape -> detect -> generate -> package).
- Manual QA for approval workflow.

## 11. Risks and Mitigations
- API instability/rate limits: retries, backoff, provider abstraction.
- Cost overruns: track each provider call and add budget checks.
- Generic output quality: tighten prompts and maintain approval gates.

## 12. Open Questions
- Which video provider is first for MVP?
- Which TTS and image providers are in-scope for MVP?
- What minimum confidence threshold should auto-surface trends for review?
- Keep this section updated before each phase.
