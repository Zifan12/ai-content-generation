# Schema lock for scale ramp

Before the corpus grows past the current 438-item bootstrap (target: 1,600 by Q3 via P1.6 recurring scrape, 5,000+ by year-end), Blueprint schema changes must be governed by a budget-aware discipline. Breaking-class changes (per ADR-0004) trigger full re-extraction; at 5,000 items the cost is ~$60 per pass, at 50,000 ~$600. Without a lock policy, exploratory schema iteration compounds linearly with corpus growth.

## Policy

**Default: additive-only.** All Blueprint schema edits after this ADR must be cache-safe per ADR-0004 (new nullable field, new Literal value, alias-preserved rename, field removal). Cache-safe edits ship without ceremony.

**Breaking changes require an ADR.** Any change in the ADR-0004 "cache-breaking" list — required-field add, Literal value removal/rename without alias, type change, SYSTEM_PROMPT structural rewrite, model swap, sampling param change — must be justified in a dedicated ADR that documents:

1. **Trigger** — what failure the current schema produces (kappa regression, missing signal for downstream consumer, etc.). A breaking change with no documented downstream pain is rejected.
2. **Cost estimate** — output of `scripts/extractor_cost_report.py --dry-run` against the current corpus, with the Anthropic prompt-cache hit rate factored in.
3. **Worth-it threshold** — concrete improvement claim (kappa delta ≥ 0.1, new niche unblocks revenue, downstream consumer eval gate moves by X). Vague "feels cleaner" is rejected.
4. **Re-extraction plan** — RQ background job, budget cap, rollback path. Foreground re-extraction blocked at >$10 estimated spend.

**Hard freeze on Tier 1 enum sets.** The eight v3.1-locked Literal[...] fields (`hook_type`, `share_hook_type`, `comment_bait_type`, `pacing`, `loop_type`, `audio_type`, `visual_complexity`, `color_mood`) plus `primary_emotion` and `duration_band` are frozen. Adding a value is allowed (cache-safe); removing or renaming is breaking and requires an ADR. Replacing the value set entirely is forbidden until v4.

**Tier 2 may evolve additively.** New free-text or nullable fields can ship on `BlueprintRecord` without an ADR provided they are cache-safe. Adding a new enum field at Tier 2 follows the v3 → v3.1 bootstrap pattern (open-string → kappa-validate → lock with ADR).

## Pre-flight check before scrape ramp (P1.6 enablement)

Before enabling recurring scrape (`P1.6` weekly cron), the following must be true:

- v3.1 Tier 1 fields frozen per this ADR
- `scripts/extractor_cost_report.py --dry-run` produces a usable estimate (verified with a 10-item sample re-extract)
- Daily budget cap configured in scrape config (e.g. `max_daily_extraction_spend: $5`)
- ExtractorResponse cache populated for all existing 438 items (already true post-8bf85bb)

## Consequences

- Schema becomes harder to iterate, by design. Trade-off favored over scale-spend exposure.
- New niches that don't fit the v3.1 enum vocabulary force either (a) staying in `aesthetic_descriptors` free-text bucket or (b) writing a breaking-change ADR. Most niches expected to fit (a).
- Mechanic miner (P1.7) and rescoped P2 retrieval must operate on the v3.1 schema as it stands. No "let me add one field to make the miner cleaner" detours without ADR.
- Re-extraction events become budgeted, scheduled, traceable. Failure mode of "I tweaked the prompt and now we owe $200" disappears.

## Considered alternatives

**Soft guideline only ("try to avoid breaking changes")** — rejected because the bootstrap discipline that produced v3.1 succeeded precisely because the v0 → v1 → v3 → v3.1 path was gated by ADRs with kappa evidence. Removing the gate at scale invites exactly the iteration churn this ADR exists to prevent.

**Wait until 5,000 items to lock** — rejected because the discipline is cheapest to enforce while the corpus is small. Adding a lock policy after a $200 wasteful re-extract is reactive; doing it now is preventative.

**Drop the lock policy and rely on per-change judgment** — rejected because the cost signal is non-local (lives in API spend, not the diff being reviewed). A written rule forces the cost check into the review path.
