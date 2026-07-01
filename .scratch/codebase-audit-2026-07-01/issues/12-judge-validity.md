# Judge validity: unpinned temperature, fixed A/B position, stats leakage, ambiguous pairwise score

Status: ready-for-human
Severity: High (AUD-H11)

Four validity defects in the eval-judge stack:

1. `src/evals/judges.py:80-84` and `:109-113` — no `temperature=0.0`. Sonnet accepts it (unlike Opus 4.7+); without it the same script scores differently across runs, flipping results near the avg ≥ 3.5 gate. Contradicts the module's own "REPRODUCIBILITY" docstring.
2. `src/evals/generation_eval.py:102-106` — RAG output always occupies slot A in pairwise comparison; any positional preference in the judge model biases `rag_win_rate` directionally against a 0.70 ship gate. The `seed` param is already reserved for the swap — wire it: random slot assignment per item, remap `preferred` back before tallying. (Currently moot — the module is import-broken, see issue 09 — but the same defect must not be rebuilt.)
3. `judges.py:70-79` — the judge is shown the SOURCE video's view/like counts while scoring a GENERATED script. Halo prime with no stated role. Drop the stats or state their role explicitly.
4. `JudgeVerdict.score` semantics in pairwise mode are undefined (score of which script?). Split pairwise into its own verdict schema without the ambiguous scalar.

Fix direction per item above. Sequencing note: judges.py's only consumer is the broken generation_eval — decide issue 09 first; if Option B (delete), retire judges.py's pairwise mode with it and rebuild both on the writer_judge pattern (anchored per-dimension rubric) when the multi-shot writer eval cycle starts.

Ready-for-human: eval-design decisions (learning-scope code + judge methodology the user owns).

## Comments
