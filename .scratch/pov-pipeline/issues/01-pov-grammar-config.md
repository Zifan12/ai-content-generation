# 01 — POV grammar block in render rules config

**What to build:** the probe-proven POV grammar becomes a reviewable, evidence-tagged block in the render rules config (`config/render_rules.yaml`, the file the render lane already treats as the rule store). Everything the compiler will later inject or enforce lives here, never in code strings: the fixed skeleton clauses (single-continuous-shot camera-as-eyes clause, unseen-protagonist device, hands-visible line, the mandatory "No cuts, no zooms, natural head movement only" constraint, the constraints block), the kill-list (dead intensifiers; "cinematic"-without-specifics; glow/glimmer → steady-intensity/diffuse as candidate-strength), beat budgets (4-6 @10s interpolated-labeled, 5-8 @15s corpus-counted), dialogue rules (never final beat, length fits seconds, plain quoted prose), and world-prose craft keys (light = time+source+named-emitter+tone, depth-layered nouns, particulates, 60-100 word body). Every entry carries an evidence tag: probe artifact path, corpus file:line, or `candidate`.

**Blocked by:** None — can start immediately.

**Status:** closed

- [x] New `pov_grammar` block present in the render rules config; yaml parses; existing consumers of the file unaffected (full test suite green)
- [x] Every line/entry has an evidence tag (probe sheet path, corpus citation, or explicit `candidate` marker)
- [x] First-person camera vocabulary marked validated-by-probe (2026-07-17 probes), superseding its CORPUS-ONLY status
- [x] The two probe prompts are reproducible from the block's clauses (manual cross-check documented in the block's header comment)
