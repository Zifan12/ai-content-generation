# Executor: orphaned spend, discarded stderr, unanchored scraping, no overwrite guard, no ceiling

Status: ready-for-human
Severity: High (AUD-H10; bundle of five defects in `src/generation/executor.py`)

1. **Orphaned spend (lines 227-234):** no try/except between the two paid create calls. Still succeeds (paid) → motion raises (`--quality high` on veo3_1 is the module's own flagged suspect) → nothing checkpointed; naive retry re-pays for the still.
2. **stderr discarded (lines 74-81):** `capture_output=True` captures the CLI's error text into `CalledProcessError.stderr`, but no caller prints it — `__str__` shows only "non-zero exit status". Diagnosing a failed paid render costs another paid render.
3. **Unanchored scraping (lines 129, 141):** `_parse_credits` takes the FIRST number in cost stdout (a leading job id/timestamp silently becomes the cost); `_extract_url` takes the FIRST URL (a progress/status URL printed before the result URL would be downloaded as the asset, no content-type check).
4. **Overwrite (lines 90-95, 229-234):** fixed filenames (`still.*`, `clip.mp4`) silently clobber prior artifacts on re-run — exactly the manual-retry scenario defect 1 creates.
5. **No ceiling (lines 211-213):** estimate is printed, nothing refuses above a threshold. Fine attended; silent-spend risk the moment this runs unattended.

Fix direction: per-job try/except that logs `e.stderr` and returns a partial `RenderResult` naming what exists on disk (minimum viable checkpoint — OpenMontage `lib/checkpoint.py` is the reference shape); anchor the cost regex to a label or use a `--json` CLI flag if one exists (verify with `higgsfield --help` before first paid run); skip-if-exists on downloads; `max_credits` parameter that raises before the first create call (ADR-0007 rule 4).

Ready-for-human: fixes are cheap but validation requires one real (paid) render; human decides when to spend it.

## Comments
