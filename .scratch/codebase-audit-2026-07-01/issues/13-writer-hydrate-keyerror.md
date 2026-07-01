# Writer crashes on a stale RAG hit (KeyError in _hydrate_hits)

Status: closed (fixed 2026-07-01 via /answer-now — `lookup.get()` + warning log on dangling hit id; degrades to the already-handled transcript=None state. tests/generation green.)
Severity: High (AUD-H12)

`src/generation/content_writer.py:197-201`: `lookup` is built from a `WHERE id IN (...)` query; a hit whose `RawContentItem` row no longer exists (index drift, deleted item) is absent from the dict, and `lookup[hit.content_item_id]` raises a bare `KeyError` — one dangling index entry kills the whole `write()` call, even though `transcript=None` is already a handled state one line later in `_build_envelope`.

Fix direction: `.get(...)` with `None` fallback + log the dangling id so index drift is visible.

Ready-for-human (not agent): `content_writer.py` is learning-scope code — user implements per the teaching contract; the fix is a one-line trace-through exercise.

## Comments
