# config/.env.example guarantees a broken first run

Status: ready-for-agent
Severity: High (AUD-H14)

Three defects in `config/.env.example`:
1. Ships `APIFY_TOKEN` — all code reads `APIFY_API_TOKEN` (`src/monitor/scraper.py:151`, `src/monitor/tools/reddit_search.py:124`, TikTok/IG scrapers). A fresh setup following the example gets "APIFY_API_TOKEN is not set" with the token sitting right there under the wrong name.
2. `DATABASE_URL=sqlite:///data/app.db` labeled "current default, backward compat" — a value `src/database.py:44-49` hard-REJECTS per ADR-0006. The example's active line crashes the app at import.
3. Missing keys entirely: `TAVILY_API_KEY` (required by `--topic` Path B), `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/`LANGFUSE_HOST` (tracing).

Fix direction: regenerate from the authoritative list — grep `os.environ` / `getenv` across `src/` + `scripts/` — with the Postgres URL as the only DATABASE_URL example and a comment per key naming what consumes it. Verified safe to edit: `config/.env` itself is gitignored and never committed (checked via `git check-ignore` + `git log --all`).

## Comments
