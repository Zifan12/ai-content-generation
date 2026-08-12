# Cost-governance contract for paid external calls

Three audited incidents share one root cause: per-call-site cost folklore instead of a contract. BUG-003 (unguarded `reddit_search`, $3.22 real spend), the ~$9.40 2026-06-29 probe burn (guard added after), and the 2026-07-01 audit's findings — `pitch_angles.py` guarding with a rate BUG-003 already disproved ($0.001844 vs $0.002), `recurring.py` rolling back the spend rows its own daily cap reads, `context_agent` accumulating estimates computed from different parameters than the calls it prices, and `run_scrape.py`/`extract_blueprints.py` spending with no guard at all. This ADR locks the rules that make paid boundaries (Apify actors, Anthropic calls, Higgsfield renders) uniform.

1. **One rate module.** Per-provider unit costs live in exactly one importable place (e.g. `src/costs.py`); no call site or docstring restates a number. A rate is recorded with the date and evidence it was verified (actor pricing page, billing console) — BUG-003/004 proved documented actor behavior requires a live-probe citation.
2. **Estimate before spend, from the call's own params.** Every paid call site computes its estimate from the same parameter values it passes to the provider (shared function or provider-returned estimate), and refuses above its threshold. Estimates derived from separate defaults are the AUD-M1 drift bug by construction.
3. **Spend records survive failure.** Any row that records money already spent (e.g. `ExtractorResponse`) is committed before an exception that aborts the run propagates. A budget guard that reads committed rows must never be the thing that rolls them back.
4. **Unattended paths get ceilings, not printouts.** Printing an estimate satisfies the render rule only when a human is watching; anything runnable by RQ/cron takes a hard cap parameter and raises above it.

## Consequences

New spend sites have a checklist instead of a convention to rediscover; the recurring failure class (4 documented instances in 3 weeks) gets a structural fix. Cost: a small `costs.py` refactor touching `reddit_search.py`, `pitch_angles.py`, `pricing.py`, `recurring.py`, `run_scrape.py`. Reversing this is cheap code-wise but re-opens the incident class.

## Considered alternatives

**Central budget service (OpenMontage's estimate→reserve→reconcile tracker)** — the right end-state for a multi-stage unattended pipeline, but heavier than v1 needs; rules 1-4 are its minimal precursor and don't preclude it.

**Rely on provider-side caps (Apify console limit, Anthropic budgets)** — kept as backstop, rejected as primary: they fail open per-run (a $9 burn fits under a monthly cap) and teach nothing to the code.
