# 04: Fridge — index Reddit text alongside web text + refresh-replace semantics

Status: closed (shipped 2026-07-17 — commit 6e971e2, Fridge.replace_topic_material() for per-topic web/Reddit indexing, 706/706 tests green)

## Scope

The fridge (`src/monitor/fridge.py`) currently indexes only the raw web text the
`ContextAgent` gathers (`index_web_text`), scoped per topic, retrieved via
topic-scoped semantic search (`retrieve`). This ticket extends the fridge into the
"universal raw-material store" the PRD calls for: Reddit reaction text — the same
raw, upvote-tagged text `ContextAgent` already gathers into `reddit_text`
(`[POST | N upvotes]` / `[COMMENT | N upvotes]` blocks) — must also be chunked,
embedded, and persisted per topic, with the upvote tags intact in the stored chunk
text (not stripped or reformatted away during chunking).

This ticket also fixes the fridge's documented duplicate-on-reindex limitation:
today, indexing a topic twice (e.g. an explicit research refresh) inserts a second
set of rows on top of the first, so `retrieve()` can return stale duplicates
alongside current facts. Refresh must instead **replace** — delete a topic's
existing fridge rows before the new indexing pass writes its rows — so a topic's
fridge always reflects only its most recent research pass.

`retrieve()`'s interface (topic-scoped semantic search, same signature and return
shape) does not change — existing callers (the grounding checker path in
`scripts/pitch_angles.py` / `src/monitor/pitch_grounding.py`) must keep working
unmodified.

Out of scope for this ticket: wiring the new Exilus research-stage driver to call
the fridge at the right point in its loop, and replacing the Topic Brief / Faction
Map artifacts on refresh (the PRD's "Pinning semantics" decision covers both
fridge rows and artifacts together, but artifact persistence is a separate typed
schema/migration — a different ticket). This ticket delivers the fridge module's
own capabilities: index Reddit text, and delete-then-index refresh — so that
ticket can call into it.

## Existing code to read first

- `src/monitor/fridge.py` — the current `index_web_text` / `_chunk_web_text` /
  `retrieve` implementation this ticket extends; its own docstring already names
  the limitation this ticket fixes ("Not idempotent: calling twice for the same
  topic inserts duplicate rows (v1 is within-run, called once per run)").
- `src/models/web_research_chunk.py` — the `WebResearchChunk` ORM row
  (`topic`, `chunk_text`, `source_url` nullable, `embedding_model`, `embedding`)
  that Reddit-sourced chunks will also populate; check whether the existing
  columns are sufficient to hold Reddit-sourced rows or something needs to change.
- `src/monitor/context_agent.py` — where `reddit_text` (raw, upvote-tagged text,
  accumulated across `reddit_search` calls) and `web_text` are threaded through
  `ContextAgentState` and both returned by `ContextAgent.run()` — the source of
  both raw-text inputs this ticket must be able to index.
- `src/monitor/tools/reddit_search.py` — confirms the exact upvote-tag format
  (`[POST | N upvotes]` / `[COMMENT | N upvotes]`, falling back to a plain
  `[POST]`/`[COMMENT]` tag when a score is unavailable) and that comments are
  already filtered to the ≥5-upvote floor before this text is ever assembled —
  relevant to what "preserved in chunk text" must survive chunking.
- `scripts/pitch_angles.py` — the current `index_web_text` call site (Path B,
  post-run, gated on `grounding_checker is not None and embedder is not None and
  not dry_run`, one shared `BgeM3Embedder` instance, injected DB session `db`) —
  shows the existing fridge-call convention this ticket's new entry point(s)
  should fit alongside without breaking.

## Decisions already locked (do not re-litigate)

- "As the operator, I want every scrap of gathered raw material (web text AND
  Reddit threads with upvote tags) indexed into the per-topic fridge, so that
  later stages and later sessions retrieve facts for free instead of
  re-scraping." (User Story 10)
- "As the operator, I want a topic refresh to REPLACE the topic's stored
  artifacts and fridge rows rather than stacking duplicates, so that retrieval
  never returns stale duplicates." (User Story 11)
- "Fridge becomes the universal raw-material store: all gathered web text AND
  Reddit reaction text (upvote tags preserved in the text) indexed per topic.
  Refresh semantics: re-research REPLACES a topic's fridge rows and artifacts
  (delete-then-index), fixing the current duplicate-on-reindex limitation.
  Retrieval interface unchanged (topic-scoped semantic search)." (Implementation
  Decisions)
- "Pinning semantics: artifacts and fridge contents are per-topic facts, written
  once; idea re-rolls never re-run research or faction reading; explicit
  refresh re-runs everything and replaces stored state." (Implementation
  Decisions)
- Testing Decisions names "fridge refresh replaces rather than stacks" as a
  specific behavior that MUST have a test.
- Seams (Testing Decisions): "injected DB session for fridge and artifact
  persistence" — no new seam type, the existing injected-session pattern.

## Acceptance criteria

1. Given a topic's raw Reddit text (containing `[POST | N upvotes]` /
   `[COMMENT | N upvotes]` tags) and that same topic's raw web text, the fridge
   indexes both into chunk rows scoped to that topic, retrievable through the
   same `retrieve(topic, query, embedder, session, k)` call — a query matching
   Reddit-only content returns a Reddit-sourced chunk, and a query matching
   web-only content returns a web-sourced chunk.
2. For any source block that carried an upvote tag, at least one retrieved
   chunk containing that block's content still contains the tag text verbatim
   — chunking never strips or reformats it.
3. Indexing a topic a second time (simulating an explicit refresh) leaves that
   topic's fridge row count equal to the second run's chunk count only — not
   the sum of both runs. The first run's rows are gone, not just outnumbered.
4. Refreshing topic A's fridge rows never deletes or alters topic B's rows —
   the delete is topic-scoped, not a global clear.
5. `retrieve()`'s signature and return shape (a `list[str]` of chunk texts,
   nearest-first, bounded by `k`, scoped to `topic`) is unchanged — existing
   callers keep working with no call-site changes required by this ticket.
6. Indexing proceeds correctly when one of the two sources (Reddit text or web
   text) is empty for a given topic — the empty source contributes zero rows
   without blocking or erroring the other source's indexing.

## Test notes

- Seams: pure chunker tests need no DB (mirrors the existing
  `test_chunk_keeps_snippets_whole_splits_big_drops_junk` /
  `test_empty_text_yields_no_chunks` pattern in `tests/monitor/test_fridge.py`
  for whatever Reddit-text chunking path is added). DB-backed behavior (index,
  retrieve, refresh-replace) uses the existing injected-`Session` +
  transactional-rollback fixture already in `tests/monitor/test_fridge.py`
  (`db` fixture: `engine.connect()` + savepoint + rollback), and the existing
  duck-typed fake embedder (`_FakeEmbedder`, deterministic seeded vectors, no
  torch/GPU) — no new seam types per the PRD's Testing Decisions.
- Must specifically cover: upvote-tag survival through chunking (AC2);
  refresh-replace leaves only the latest run's rows for the refreshed topic
  (AC3); refresh scoped to one topic never touches another topic's rows (AC4);
  empty-source indexing doesn't error or block the other source (AC6);
  `retrieve()` return shape/signature is unchanged so existing callers
  (grounding checker) are undisturbed — a regression here would silently break
  `scripts/pitch_angles.py` and `src/monitor/pitch_grounding.py` without this
  ticket touching either file.
- Not this ticket's job to test: the Exilus research-stage driver's call
  ordering (when refresh vs. append is decided), or Topic Brief / Faction Map
  replace-on-refresh — those belong to the research-stage ticket(s).

## Who types

Decision-bearing: how Reddit text is chunked (reuse vs. adapt
`_chunk_web_text`, and whether the upvote-tag survival constraint changes that
function), what the delete-then-index refresh entry point looks like (a new
function, a parameter on the existing one, or something else), and whether
`WebResearchChunk` needs a new column to distinguish source — this is
`src/monitor/` business logic the user implements per the repo's teaching
model (gate model applies: user decides the interface/refresh-call shape
before implementation, or drafts it and predicts/traces edge cases after).
Pure-ops sub-parts are AI-typed-by-default: an Alembic migration if a new
column is added, and any `providers.yaml`/embedder-wiring boilerplate at the
`scripts/pitch_angles.py` call site.

## Open questions

- The PRD does not say whether Reddit-sourced rows need a distinguishing field
  on `WebResearchChunk` (e.g. a `source_kind` column) or whether topic-scoping
  plus the upvote tag already present in the chunk text is sufficient to tell
  Reddit rows from web rows at retrieval time. Left to implementation.
- The PRD does not say whether the `WebResearchChunk` model/table name changes
  now that the fridge indexes more than web text ("the fridge becomes the
  universal raw-material store" is a role change, not a stated rename). Left
  to implementation; a rename is a bigger diff (migration + every call site)
  than reusing the existing table, so this should be a deliberate, not
  incidental, decision.
- The PRD does not specify the exact refresh trigger/entry-point shape (e.g. a
  `reindex_topic(topic, reddit_text, web_text, embedder, session)` that always
  deletes-then-inserts, vs. a separate explicit `delete_topic()` the caller
  invokes before calling `index_web_text`/a new Reddit-indexing function
  twice). Left to implementation.
