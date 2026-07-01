# Codebase Audit 2026-07-01 — Findings Tracker

Source of truth: `docs/audits/2026-07-01-full-codebase-audit.md` (severity-tagged, file:line-anchored, includes the Prompt Engineering Audit and Medium/Low findings not tracked as individual issues here).

This directory tracks the Critical/High findings that need work items. Two Criticals live in `bugs.md` instead (BUG-005 wrong cost-guard rate, BUG-006 sqlite-dialect upsert) because they are concrete reproducible bugs matching that log's format.

| # | Issue | Sev | Status |
|---|---|---|---|
| 01 | executor shell injection | Critical | FIXED 2026-07-01 (validation rides next paid render) |
| 02 | recurring.py budget rollback + exception swallow | Critical+High | ready-for-agent (dormant path — defer to P4 reactivation) |
| 03 | tiktok fetch_trending tuple return | Critical | ready-for-agent (dormant path — defer to P4 reactivation) |
| 04 | --topic --no-llm flag ignored | High | closed (fixed 2026-07-01) |
| 05 | spending scripts missing guards | High | ready-for-agent |
| 06 | extractor fingerprint drift | High | ready-for-agent |
| 07 | extractor envelope hardening (cache-coupled) | High | ready-for-human |
| 08 | pricing not model-keyed | High | ready-for-agent |
| 09 | generation_eval rot (rewrite vs delete) | High | needs-triage |
| 10 | render routing disconnected (locked-decision tension) | High | ready-for-human |
| 11 | executor robustness bundle | High | ready-for-human |
| 12 | judge validity bundle | High | ready-for-human |
| 13 | writer hydrate KeyError | High | ready-for-human |
| 14 | test debt on live paths | High | needs-triage |
| 15 | .env.example stale | High | ready-for-agent |
| 16 | rag indexer batching | High | ready-for-human |
| 17 | hybrid retrieval missing BM25 | High | needs-triage |

ready-for-human is used here both for human-decision items AND for learning-scope code the user implements per the CLAUDE.md teaching contract (issues 12, 13, 14, 16). ready-for-agent = ops/tooling scope.

Pending separate approval (stop conditions): CLAUDE.md diff (in the audit report), ADR-0007 draft (in the audit report appendix).
