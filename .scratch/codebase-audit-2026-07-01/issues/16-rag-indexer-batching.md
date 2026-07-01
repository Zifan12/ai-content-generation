# RAG indexer: N+1 existence checks; one bad batch discards the whole embedding run

Status: ready-for-human
Severity: High (AUD-H15)

Two defects in `src/rag/indexer.py`:
1. **N+1 (lines 76-79):** one SELECT per candidate row to decide skips — every indexing run round-trips per row even when nothing changed. Direction: one `WHERE content_item_id IN (...)` batch-fetch into a set/dict before the loop.
2. **All-or-nothing commit (lines 88-110):** embedding loop commits once at the end; a transient failure in batch N (CUDA hiccup, bad text) raises before the commit — every prior batch's GPU work is discarded, and retry re-embeds the corpus since nothing persisted for `only_missing` to skip. Direction: commit per embedding batch so runs resume. (VRAM context: batch=8 is a deliberate 4070 cap — per-batch commits also shrink the blast radius of an OOM.)

Ready-for-human: retrieval code is learning-scope; user implements.

## Comments
