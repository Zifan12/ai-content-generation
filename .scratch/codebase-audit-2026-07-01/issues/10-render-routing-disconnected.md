# Model-routing table + render guardrail constraints are dead code; every render is veo3_1

Status: ready-for-human
Severity: High (AUD-H9)

`src/generation/render_adapters/rules.py:45-54` (`route()`) and `:82-83` (`global_constraints()`) have no callers outside their own tests (repo-wide grep, cross-confirmed against full reads of `adapter.py` and `content_writer.py`). Runtime path: `render_jobs()` takes `package.model_cli_id` directly; the writer defaults it to `"veo3_1"` (`content_writer.py:279`); `smoke_content_writer.py`'s separate `_BACKEND_TO_MODEL` dict also falls back to veo3_1.

Consequences:
1. The `routing:` block in `config/render_rules.yaml` (impossible_physics → Hailuo/Seedance before Veo — backed by paid render evidence that Veo fails impossible end-states) never influences any render. This is the LOCKED per-shot MODEL_ROUTING decision (`render_taste_test/MODEL_ROUTING.md`, DECISIONS_LOCKED.md) existing in yaml + tests only — flagged as a locked-decision tension, not overridden.
2. The anti-defect constraint buckets (`always_append`, twin-suppression, watermark, audio cleanliness) reach no prompt — known-defect suppressions absent from every paid render.

Fix direction: writer emits a motion-classification tag (it already reads the premise) → `model_cli_id = rules.route(tag)[0]` before stamping the package; `render_jobs()` appends `rules.global_constraints(kind, style)` to each prompt. PREREQUISITE conflict to resolve first: `always_append` includes "no on-screen text or subtitles" which contradicts the writer's `onscreen_text` field — scope that constraint to the rendered frame (hook text is a manual upload overlay anyway) before wiring, or it fights the schema.

Ready-for-human: touches the locked routing decision + the writer (learning code).

## Comments
