# PRD: Exilus — topic-to-slate front-end (research → faction map → wide idea slate)

Status: ready-for-agent
Date: 2026-07-17
Origin: brainstorm + grill session 2026-07-17 (design decisions locked one-by-one with user);
second-brain consults (Indi Young audience-listening; Azure/Commey/Huyen agent patterns)

## Problem Statement

I name a topic I want content about, but the current front-end keeps handing me bad idea
slates. The root causes, proven with data:

- The audience read is unstable: the same Reddit thread was re-read into six different
  "consensus" summaries across runs. One run's read produced a pitch I liked; another run's
  read on the same thread produced ideas I hated.
- A single-consensus read collapses a mixed audience into one voice. Real threads contain
  multiple camps wanting different things; forcing one `audience_want` loses the landscape.
- Research effort is thrown away. Raw gathered material dies inside the run, so any
  downstream question ("what does this character's home look like?") or any re-pitch
  re-spends scraping and LLM money to re-learn what a previous run already knew.
- I can't see or correct what the system believed before ideas were generated. By the time
  I see output, a bad audience read has already poisoned the slate.
- Idea slates are narrow (2-3), so one bad roll leaves me nothing to pick from.

## Solution

A staged front-end ("Exilus") with three pinned, human-inspectable artifacts:

1. I name any subject (character, show, game, arc — no freshness requirement).
2. **Research**: Exilus runs the existing capped research loop (web + Reddit) until it can
   pass a "can-explain" test — five named brief fields, each backed by a source citation —
   graded by code checks plus a cheap cross-family LLM checker, never by itself.
   Output: a pinned **Topic Brief**.
3. **Faction read**: Exilus maps the audience into camps that emerge from the comments
   themselves (capped at 5 after emergence, single camp legal). Each camp records its
   feeling, surface want (their words), inferred deeper desire (marked as inferred),
   evidence quotes with upvote counts, and weight. Output: a pinned **Faction Map**.
4. **Ideation**: Exilus reads ONLY the two pinned artifacts and emits a wide slate of
   8-15 one-line video ideas spanning camps and modes. I pick winners; the pick feeds the
   existing downstream director (StoryArchitect) unchanged.

Pinning: brief + map are saved once per topic. Idea re-rolls re-run ideation only — same
world-read every time, near-zero cost. An explicit refresh re-runs research and REPLACES
the stored artifacts and fridge contents. Everything gathered along the way (web text and
Reddit threads, upvote tags intact) is indexed into the per-topic fridge so any later stage
retrieves facts instead of re-scraping.

## User Stories

1. As the operator, I want to hand Exilus any named subject, so that I am not limited to
   topics currently trending.
2. As the operator, I want research to proceed regardless of whether the topic has a live
   reaction wave, so that quiet/evergreen topics still produce content ideas.
3. As the operator, I want the Topic Brief to answer five fixed questions (what is this;
   what recently happened; key characters + relationships; why people care; open unknowns),
   so that I can trust one consistent research contract per topic.
4. As the operator, I want every brief field to cite the source it came from, so that I can
   verify any claim instead of trusting the model's memory.
5. As the operator, I want the brief graded by code checks plus a separate cheap
   cross-family LLM checker (never the researcher grading itself), so that a vague brief
   cannot certify itself as done.
6. As the operator, I want a failed brief field to send its gap back into the research loop
   as the next query (max 2 repair rounds), so that the loop converges instead of retrying
   blindly.
7. As the operator, I want research bounded by the existing caps (tool calls, Apify spend,
   stale-streak), so that a thin topic cannot loop forever or burn budget silently.
8. As the operator, I want a brief that still fails after the caps to be written anyway
   with failing fields stamped UNVERIFIED and the run halted for me, so that I decide
   whether to fix, continue, or kill — never a silent proceed on bad research.
9. As the operator, I want a passing brief to flow onward with no mandatory approval click,
   so that clean runs have no friction.
10. As the operator, I want every scrap of gathered raw material (web text AND Reddit
    threads with upvote tags) indexed into the per-topic fridge, so that later stages and
    later sessions retrieve facts for free instead of re-scraping.
11. As the operator, I want a topic refresh to REPLACE the topic's stored artifacts and
    fridge rows rather than stacking duplicates, so that retrieval never returns stale
    duplicates.
12. As the operator, I want audience camps to emerge from the comments themselves rather
    than being forced into a preset count, so that the map reflects the thread, not the
    schema.
13. As the operator, I want at most 5 camps kept (filtered after emergence) and a single
    camp to be legal when the audience is unanimous, so that the map is honest in both
    directions.
14. As the operator, I want each camp to record feeling, surface want in the audience's own
    words, and the inferred deeper desire explicitly marked as inferred, so that I can
    distinguish what fans said from what Exilus guessed.
15. As the operator, I want each camp to carry evidence quotes with their upvote counts and
    a weight (share of surviving comments), so that I can judge how real and how big each
    camp is.
16. As the operator, I want the faction map built only from comments that survived the
    existing ≥5-upvote floor, so that zero-engagement comments never shape camps.
17. As the operator, I want the faction stage to reuse the comments research already
    fetched, topping up with at most one extra scoped Reddit call when volume is short, so
    that the common case costs nothing extra.
18. As the operator, I want a faction map built on too little data stamped THIN DATA, so
    that I know when camps stand on little evidence.
19. As the operator, I want ideation to read ONLY the pinned brief and map, so that every
    idea is traceable to an artifact I can inspect — no hidden context.
20. As the operator, I want a slate of 8-15 one-line ideas with every camp represented at
    least once and each idea tagged with its target camp and mode, so that I can skim the
    whole landscape and pick with my own taste.
21. As the operator, I want idea re-rolls to reuse the pinned artifacts and be shown prior
    ideas with an instruction not to repeat them, so that "more ideas" is cheap and fresh.
22. As the operator, I want to read and correct the brief and the faction map before or
    after any run, so that my knowledge of the fandom can override a wrong read before it
    poisons ideas.
23. As the operator, I want my picked idea to hand off in the existing pick-level contract,
    so that the downstream director, gates, and writer keep working unchanged.
24. As the operator, I want the faction-map prompt validated once at build time by a
    shuffle-stability test (same camps from shuffled/subsampled comments), so that I know
    the instability that killed the old gap reads is actually fixed, not repainted.
25. As the developer, I want every stage testable with fake LLM responses, fake fetcher
    items, and an injected DB session, so that the full pipeline is provable without
    network, credits, or spend.

## Implementation Decisions

All decisions below were put to the user individually and ratified (grill session
2026-07-17).

- **Three pinned artifacts** — Topic Brief, Faction Map, Idea Slate — with typed schemas;
  ideation is information-bottlenecked to the two upstream artifacts. (Endorsed by
  second-brain consult: staged typed artifacts over one continuous agent context;
  pinning doubles as checkpointing.)
- **Research stage extends the existing context-gathering loop** (LangGraph plan/act loop,
  Reddit + Tavily + Firecrawl tools, community lookup). Existing caps unchanged: 20 tool
  calls, $1.00 Apify per run, 3-stale-Reddit-calls saturation guard, reaction+context floor.
- **Topic Brief schema**: five fields — identity, recent events, key characters and
  relationships, why people care, open unknowns — each with source citations. Open
  unknowns carries forward the existing unresolved-facts concept. No wave_status field
  (user decision). No visual/lore-dump fields (belong downstream).
- **Checker is two-layer and never self-graded**: (1) code checks — field non-empty,
  citation present and drawn from the actually-gathered URL set; (2) one cheap
  cross-family LLM call judging per-field specificity (repo's existing judge-seat
  convention). Max 2 fail-and-repair rounds; each failed field's gap becomes the next
  research query. On exhaustion: brief persisted with UNVERIFIED stamps, run halts for the
  operator. Passing brief: no blocking gate.
- **Fridge becomes the universal raw-material store**: all gathered web text AND Reddit
  reaction text (upvote tags preserved in the text) indexed per topic. Refresh semantics:
  re-research REPLACES a topic's fridge rows and artifacts (delete-then-index), fixing the
  current duplicate-on-reindex limitation. Retrieval interface unchanged (topic-scoped
  semantic search).
- **Faction Map replaces the single-consensus gap analysis** for this lane. Camp emergence
  is unconstrained during generation; a cap of 5 is applied afterward as a filter. Single
  camp legal. Camp record fields: name, feeling, surface_want (audience's words),
  deeper_desire (marked INFERRED), evidence quotes with upvote counts, weight (share of
  surviving comments). Built from comments already fetched during research (which already
  pass the ≥5-upvote floor at the tool layer); if surviving-comment volume is below floor
  (~30), at most ONE additional scoped Reddit call tops up; still short → THIN DATA stamp
  on the map. (Consult basis: Indi Young — emergent segmentation, surface-vs-interior
  wants, size as triage signal only; known depth ceiling of unprompted forum text accepted
  and documented, not papered over.)
- **Ideation stage reshapes the existing slim pitcher**: input becomes the two artifacts
  (not event + gap), slate grows from 2-3 to 8-15 one-line ideas, every camp covered at
  least once, remaining allocation free; each idea tagged with target camp + mode. Idea
  record keeps the existing pick-level contract so the downstream director (StoryArchitect
  D1), craft gates, and writer are untouched. Re-rolls: same pinned inputs, prior loglines
  passed as do-not-repeat.
- **Pinning semantics**: artifacts and fridge contents are per-topic facts, written once;
  idea re-rolls never re-run research or faction reading; explicit refresh re-runs
  everything and replaces stored state. (Generalizes the ratified gap-pin decision.)
- **Persistence**: artifacts stored as JSON columns on the topic's event/topic record,
  following the existing idea_json/story_json precedent; exact column layout decided at
  implementation time via migration.
- **The old single-consensus gap agent stays in place for the legacy lane** until this lane
  proves out; Path A (subreddit scraper → event extractor → idea-fit gate) is sidelined for
  this lane, not deleted.
- **Human control points**: operator can read/correct both artifacts at any time; forced
  halt only on UNVERIFIED brief; operator picks at the slate.
- **Known boundary, explicitly deferred**: research tools ingest live web text — a poisoned
  page could ride into the pinned brief (indirect prompt injection). Noted, not mitigated
  in this spec.

## Testing Decisions

- Tests assert external behavior only: given canned inputs, the stage produces the right
  artifact shape/content and the right control flow (halt, top-up, stamp, re-roll dedup) —
  never internal call order or prompt wording.
- Seams (all pre-existing patterns, no new seam types):
  - fake/injected LLM per stage (research planner, checker, faction reader, ideator) —
    the pattern every monitor-agent test already uses;
  - injected item_fetcher fakes for Apify/Tavily/Firecrawl — no network in tests;
  - injected DB session for fridge and artifact persistence;
  - top seam: the pipeline driver — topic in → slate out with all fakes injected,
    mirroring the existing wire test.
- Specific behaviors that MUST have tests: checker fails a citation-less field; checker
  repair loop respects the 2-round bound; UNVERIFIED + halt path; fridge refresh replaces
  rather than stacks; faction top-up triggers exactly once and only below floor; THIN DATA
  stamp; camp cap applied post-emergence; single-camp map accepted; slate covers every
  camp; re-roll excludes shown ideas; pick hands off in the existing contract.
- Build-time (paid, manual, not CI): shuffle-stability validation of the faction prompt on
  2-3 real threads — same camps must re-emerge from shuffled/subsampled comments before the
  prompt is trusted; repo's existing ablation methodology (n≥4, user judges blind) applies
  to any subsequent prompt tuning.
- Prior art: existing monitor-agent unit tests (fake LLM), scraper/tool tests (fake
  fetcher items), the smoke wire test, and the repitch gap-pin tests.

## Out of Scope

- Everything downstream of the pick: StoryArchitect (D1), craft gates, writer, render
  executor, and all render-lane decisions (explicit user instruction: "forget everything
  about rendering for now").
- Staged-director slices ② ③ ④.
- Path A auto-discovery lane (scraper → event extractor → idea-fit gate) — untouched,
  neither extended nor removed.
- Multi-platform reaction sources (YouTube, X, TikTok) — Reddit-first locked for this spec.
- Prompt-injection hardening of the research loop (documented boundary).
- Runtime stability double-rolls of the faction read (build-time validation only).
- Prompt-text ratification: system prompts are AI-drafted and user-ratified per repo
  convention, at implementation time, not in this spec.
- Cost/model seat changes beyond adding the checker seat (seat wiring follows the existing
  providers.yaml convention).

## Further Notes

- **Hard prerequisite**: the ~40-file uncommitted slice ① working tree (staged-director,
  2026-07-16) must be committed before implementation starts. Proposed split already on
  the table from the 2026-07-16 session: (1) content-writer prompt cleanup, (2) slice ①,
  (3) gap pin + pitch-54 cleanup.
- This spec IS the "gap-analysis quality detour" queued at the end of the 2026-07-16
  session, done as a redesign rather than a patch: the unstable single-consensus read is
  replaced by pinned, evidence-weighted faction structure; the ideation stage gets the
  breadth (8-15) the old 2-3 slate lacked.
- Naming: "Exilus" is the user's working name for the front-end model/flow; module naming
  at implementation time follows existing repo conventions.
- Cost expectation per fresh topic run: existing research caps dominate (≤$1 Apify + a few
  LLM seat calls); faction + ideation add LLM-only cost; re-rolls are LLM-only on the
  ideation seat. No render credits anywhere in this lane.
- Depth ceiling accepted: unprompted forum text cannot reach interview-grade audience
  insight (no follow-up questions possible). deeper_desire is a best-effort inference,
  always labeled, never silently treated as fact.
