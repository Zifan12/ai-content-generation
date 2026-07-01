# recurring.py: budget guard rolls back its own spend records; all exceptions swallowed

Status: ready-for-agent
Severity: Critical + High (AUD-C3, AUD-H4)

Two defects in `src/scrapers/recurring.py`:

1. **AUD-C3 (Critical):** `db.commit()` (line 138) runs only on clean loop completion. The `BudgetExceeded` handler (lines 140-142) re-raises without committing; `extractor.extract()` only flushes. Session close rolls back every billed `ExtractorResponse` row from the job — `today_extraction_spend()` (committed rows only) then under-counts, and the next RQ invocation spends toward the cap again. Real money spent, DB forgets it.
2. **AUD-H4 (High):** lines 144-145 `except Exception as e: result["error"] = str(e)` — no traceback log, no re-raise. RQ marks failed jobs succeeded.

Fix direction: commit spend rows before the `BudgetExceeded` re-raise (or commit per extraction inside the loop); replace the broad swallow with `logging.exception(...)` + re-raise so RQ's failure queue engages. Regression test: budget trips mid-loop → assert the pre-trip `ExtractorResponse` rows are still queryable in a fresh session.

Related: proposed ADR-0007 rule 3 ("spend records survive failure").

## Comments
