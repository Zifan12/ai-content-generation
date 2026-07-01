# Spending scripts with no pre-flight cost guard

Status: ready-for-agent
Severity: High (AUD-H3)

Guard-less spend paths, in descending exposure:

1. `scripts/run_scrape.py:81-84` — `--limit` (default 50) unbounded; omitting `--niche` multiplies by every active niche; `TikTokScraper.fetch_trending` has a time cap but no dollar cap. Exact incident class of the documented ~$9.40 and $3.22 burns.
2. `scripts/extract_blueprints.py` — default `--limit 50` unguarded Anthropic calls.
3. `scripts/run_self_agreement.py` — 2× extract per item (default 20 → 40 calls), unguarded.

Fix direction: port the estimate-then-refuse pattern from `pitch_angles.py:442-457` (with the corrected per-actor rate — see BUG-005) into each `main()`; for LLM scripts use `extractor_cost_report.py`'s median-cost dry-run estimator as the per-call number. Once ADR-0007 lands, all three import from the single rates module.

## Comments
