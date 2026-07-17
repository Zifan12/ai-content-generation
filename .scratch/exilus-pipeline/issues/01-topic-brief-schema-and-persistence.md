# 01: TopicBrief typed schema + per-topic persistence

Status: closed (shipped 2026-07-17 — commit 6e971e2, TopicBrief model + migration dbac9327ac96, 706/706 tests green)

## Scope

This ticket builds the **TopicBrief** artifact's data layer only: a typed Pydantic
schema for the five PRD-mandated brief fields (identity, recent events, key
characters and relationships, why people care, open unknowns), each carrying its
own source citation(s), plus a representable **UNVERIFIED** stamp for any field
that fails the (separately-ticketed) checker after its repair rounds are
exhausted. It also builds the persistence path for that schema: a JSON column
following the existing `idea_json`/`story_json` precedent (`AnglePitchRecord`),
added via an Alembic migration, written once per topic and fully **replaced**
(delete-then-write, never stacked) on an explicit refresh.

Out of this ticket's scope: the research/context-gathering loop that produces
the brief's content, the two-layer checker (code checks + cross-family LLM
judge) that grades it, the repair-loop that re-queries on a failed field, and
the fridge indexing of raw gathered material. Those are separate tickets that
will call into the schema and persistence this ticket produces.

Sibling-artifact persistence ownership (coverage audit 2026-07-17): the
FactionMap's persistence lives in ticket 05, mirroring this ticket's pattern
and following this ticket's table-placement decision. The Idea Slate needs NO
new persistence — slate ideas already persist as individual `AnglePitchRecord`
rows (`idea_json`), and re-roll dedup reconstructs its do-not-repeat list from
those rows (ticket 07). This ticket is the schema/table AUTHORITY the other
two follow; ticket 02 consumes this ticket's `TopicBrief` shape verbatim.

This ticket does **not** decide which SQLAlchemy table the new column(s) land
on. The PRD explicitly defers "exact column layout" to implementation time, and
no per-topic table exists yet in `src/models/` — `TrendingEventRecord` is
event-scoped (tied to a scraped headline/subreddit/virality window), not the
freshness-agnostic per-topic record Exilus needs (a topic can be named with no
live reaction wave at all). That placement decision is this ticket's first
fork — see Open questions.

## Existing code to read first

- `src/monitor/schemas.py` — the `extra="forbid"` LLM-response-model convention
  already used for `GapAnalysis`/`ContextSynthesis`/`ContextBundle`; `TopicBrief`
  should mirror this shape, and this is the file it most likely lives in.
- `src/models/trending_event.py` — the only existing per-topic-ish record; it
  already carries `context_bundle` and `unresolved_facts` as nullable JSON
  columns, which is the closest existing precedent for "open unknowns" but the
  record itself is event-scoped, not topic-scoped — read it to see exactly
  where that scoping lives and what would have to change to host a brief.
- `src/models/angle_pitch.py` — the `idea_json`/`story_json` precedent this
  ticket's persistence must follow: a nullable JSON column, a comment
  explaining what NULL means, and a column written by a specific pipeline
  stage (not the same stage that reads it later).
- `alembic/versions/a7c2e91d4b58_add_idea_json_to_angle_pitches.py` — the exact
  migration shape (single reversible `add_column`/`drop_column`) to mirror for
  the new column(s) this ticket adds.

## Decisions already locked (do not re-litigate)

- Topic Brief schema is exactly five fields: identity, recent events, key
  characters and relationships, why people care, open unknowns — each with
  source citations.
- No `wave_status` field (user decision). No visual/lore-dump fields — those
  belong downstream, out of scope here.
- Open unknowns carries forward the existing unresolved-facts concept (compare
  `TrendingEventRecord.unresolved_facts` / `ContextSynthesis.unresolved_facts`).
- On checker exhaustion (max 2 fail-and-repair rounds — checker logic is a
  separate ticket), the brief is persisted anyway with failing fields stamped
  UNVERIFIED and the run halts for the operator; a passing brief flows onward
  with no blocking gate.
- Pinning semantics: the brief is a per-topic fact, written once; idea re-rolls
  never re-run research; an explicit refresh REPLACES the stored artifact
  (delete-then-index/write), never stacks or duplicates.
- Persistence follows the existing `idea_json`/`story_json` JSON-column
  precedent; the exact column layout is explicitly left to implementation
  time (not decided in the PRD).
- Human control point: the operator can read and correct the brief at any
  time; forced halt applies only on an UNVERIFIED brief.
- Research tooling ingests live web text — a poisoned page riding into the
  pinned brief (indirect prompt injection) is a documented, deferred boundary,
  not mitigated by this ticket.

## Acceptance criteria

1. A `TopicBrief` schema instance can be constructed with all five required
   fields (identity, recent events, key characters and relationships, why
   people care, open unknowns) populated, and rejects unknown/extra fields
   (`extra="forbid"`, matching the repo's LLM response-model convention).
2. Each of the five fields carries at least one source citation distinguishable
   from the field's own content (a field's text and its citation(s) are
   separately inspectable, not concatenated into one string).
3. Any single field can be marked UNVERIFIED independently of the others — a
   brief where field A is fully cited and field B is UNVERIFIED is a valid,
   constructible instance (this is the shape the checker-exhaustion path in a
   later ticket will produce; this ticket only has to make it representable).
4. A citation carries something URL-identifiable (e.g., a URL string) so that
   a downstream checker (built separately) can later verify "citation drawn
   from the actually-gathered URL set" without requiring a schema change.
5. Persisting a `TopicBrief` for a topic writes it to the new JSON column(s)
   and reading it back reconstructs an equal `TopicBrief` (round-trip).
6. Persisting a second brief for the same topic (the refresh path) REPLACES
   the stored value — a read after the second write returns only the second
   brief's content; nothing from the first write survives or merges in.
7. The Alembic migration's `upgrade()` adds the new column(s); `downgrade()`
   drops them cleanly and reversibly (mirrors `a7c2e91d4b58`).
8. Pre-existing rows and tests untouched by this ticket (`angle_pitches`
   `idea_json`/`story_json`, `trending_events` `context_bundle`) still load
   and pass unchanged — the new column(s) are additive and nullable.

## Test notes

- No LLM or network seam is needed for this ticket — it is pure Pydantic
  schema-validation tests plus persistence tests against an injected/test DB
  session (the existing SQLAlchemy session-fixture pattern already used by
  `tests/monitor` and `tests/models`).
- PRD-mandated behaviors this ticket's tests must cover: a brief with all
  fields verified persists with no stamps; a brief with one or more fields
  UNVERIFIED is constructible and persists as such; a refresh write REPLACES
  rather than stacks (this ticket proves the artifact half of that guarantee —
  the fridge half is a separate ticket); round-trip equality survives a
  write/read cycle; migration `upgrade`/`downgrade` are both exercised.
- Explicitly out of this ticket's test scope, even though the PRD's Testing
  Decisions section names them: checker pass/fail logic, the 2-round repair
  bound, research-loop query generation, faction map behavior, ideation. This
  ticket only proves the schema + persistence primitive those stages sit on —
  do not stub or partially test the checker here.

## Who types

The `TopicBrief` schema shape and the UNVERIFIED-representation design are
decision-bearing (a new schema with no single existing file to mirror 1:1) —
user-implements, AI reviews, per the repo's gate model. The persistence wiring
(adding a nullable JSON column, read/write round-trip) is a named-mirror of
`AnglePitchRecord.idea_json` in `src/models/angle_pitch.py` — AI-typed-by-default
under the named-mirror carve-out, though the user still owns the fork of
*which* table the column lives on (see Open questions). The Alembic migration
itself is pure ops boilerplate — AI-typed-by-default, mirroring
`a7c2e91d4b58_add_idea_json_to_angle_pitches.py` line-for-line in shape.

## Open questions

- Which table hosts the brief column(s): extend `TrendingEventRecord` (already
  has `context_bundle`/`unresolved_facts`, but is event-scoped) or introduce a
  new topic-scoped record (Exilus topics have no freshness requirement)? The
  PRD explicitly defers this ("exact column layout decided at implementation
  time via migration") — not decided here.
- Internal shape of the UNVERIFIED stamp: a per-field boolean/enum flag next to
  each field's citation(s), a single freeform status string, or a small
  wrapper sub-model per field (value + citations + verified flag)? The PRD
  specifies the behavior, not the schema shape.
- Citation shape itself: a bare URL string, a `{url, quote}` pair, or an index
  into fridge-indexed source rows (the fridge doesn't exist yet — it's a
  separate ticket)? The PRD says "each with source citations" and (in the
  checker bullet) "drawn from the actually-gathered URL set," but does not fix
  the field's concrete type.
- Structure of "key characters and relationships": a list of structured
  records (name + relationship description) versus one prose field? The PRD
  names it as one of five fields but does not specify internal shape.
- Naming: the PRD says "module naming at implementation time follows existing
  repo conventions" — exact class/column names (e.g. `TopicBrief` vs.
  `TopicBriefRecord`, `topic_brief_json` vs. `brief_json`) are not prescribed.
