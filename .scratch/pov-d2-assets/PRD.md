# PRD: POV Pipeline — D2 asset stage (object references)

Status: ready-for-agent
Date: 2026-07-23
Evidence base: post #3 live run (2026-07-22, published id=6) — probe A/B/C forensics in `output/pov/20260722_143328_*/render_sheet.md` operator-corrections log; validated object-ref recipe (element refs + motion-only prompt = motion restored, "best video so far"; full-composition ref = static hijack, pitch-51 class); blur root cause (upscaled 480p probe posted as final; corpus + web research: upscalers cannot add detail, finals must be native-res). Design ratified via brainstorm + grilling session 2026-07-23; every fork below user-answered.

## Problem Statement

Post #3 proved two things the pipeline does not yet do. First: when a story's world contains invented fantastical objects (a rising hell metropolis, an inverted heaven city), text-only prompts hit the model's generic prior and the world reads "plain" — the fix that worked (reference stills for the objects, element refs only, motion kept in prose) was done entirely by hand: still generation, approval, cropping, prompt rewriting, and command editing all happened outside the pipeline, so the verdict flow released a stale `final_command.txt` carrying the original ref-less prompt. Second: the posted video was blurry because the "final" was a 0.1cr upscale of the 480p probe; the render ladder allowed a draft-salvage tool to produce a keeper. Both lessons are paid for; neither is enforced by tooling.

## Solution

Extend the POV lane's existing asset machinery (slice ② character gate) with an operator-declared object-reference stage, and fold the validated recipe plus the corrected render ladder into the lane's config and verdict flow:

1. **Operator declares objects pre-render.** A repeatable `--object <slug>` argument names each invented world element that would hit the generic prior (the call stays human — this session proved the operator knows before any spend). Ordinary objects need no flag; text handles them.
2. **Script seat writes per-object world descriptions in structured fields.** The compiler never performs prose surgery: an object's description is a schema field, so replacing it with a reference binding is a field drop, not lexical matching (spine-check lesson: lexical checks cannot read prose).
3. **Pipeline generates candidate stills, operator picks keepers.** For a declared object with no references on disk, the pipeline states cost, runs GPT Image 2 per object (deterministic template prompt: the object's description + a shared style clause + vantage derived from the scene; never the composed target frame), writes candidates into the object's reference directory, and halts with a pick sheet. The operator promotes keepers; the gate then passes. Characters keep slice ② behavior unchanged (canon must match; never generated).
4. **Motion-only compile when object refs bound.** Each bound object compiles to one positional binding sentence (`imageN` convention); its world description is dropped from the body. Action beats, camera, style, and audio compile exactly as today — refs carry look, prose carries motion (the probe-C recipe as code).
5. **Verdict flow releases the truth.** The final command is derived from the run's actual compiled prompt and reference set (staleness fixed structurally — refs now live inside the run); the probe-PASS hash covers prompt + ordered reference list, so a ref swap invalidates a prior PASS.
6. **Ladder and brakes corrected.** 480p probe → operator watch → native **1080p ×1** final with refs attached; a second take is an operator judgment via the existing logged override, never a default. Upscaler demoted to draft salvage. Per-story cap raised 150→300 credits; still spend counts toward the tally.

## User Stories

1. As the operator, I want to declare invented world objects by slug when I start a run, so that the generic-prior call stays mine and is made before any credits are spent.
2. As the operator, I want ordinary objects to need no declaration, so that text-only remains the default and refs stay the exception (asset routing rule).
3. As the operator, I want the script seat to receive my declared object list and write each object's world description in its own structured field, so that downstream stages can act on a specific object without parsing prose.
4. As the operator, I want a declared object with no references on disk to trigger candidate still generation instead of a "drop images yourself" request sheet, so that invented objects (which have no canon to fetch) get assets without me leaving the pipeline.
5. As the operator, I want the pipeline to state the total still-generation cost before spending, so that image spend follows the same cost-governance rule as every other paid call.
6. As the operator, I want each object's still generated in isolation from a deterministic template (description + shared style clause + scene vantage), so that no LLM seat is added and every object in a batch shares one style register.
7. As the operator, I want the still prompt to never include the composed target frame (no basket, no hands, no full staging), so that the probe-B static-hijack failure cannot be rebuilt into the assets.
8. As the operator, I want generated candidates written into a per-object candidates area and the run to halt with a pick sheet, so that no reference reaches a render without my eyes on it.
9. As the operator, I want to promote a keeper by moving it up into the object's reference directory and re-running, so that the approval gesture is a file operation, not a new UI.
10. As the operator, I want the asset gate to validate object reference directories with the same loud-failure rules as characters (missing/empty = halt with guidance; invalid contents = error), so that a malformed ref set never reaches a paid render silently.
11. As the operator, I want candidate files ignored by the gate's validation of the reference directory, so that unpromoted candidates never count as approved references.
12. As the operator, I want references uploaded in a deterministic order (characters first, then objects, declaration order), so that the `imageN` positional numbering is a stable contract across stages.
13. As the operator, I want each bound object to compile to exactly one positional binding sentence naming its image slot, so that the render model is told which image carries which object's look.
14. As the operator, I want a bound object's world description dropped from the compiled body — binding sentence substituting, never both — so that two descriptions of one thing cannot fight on screen (pitch-51 camera-hijack class).
15. As the operator, I want an undeclared-object story to compile exactly as today, so that the text-only path carries zero regression risk.
16. As the operator, I want binding sentences exempt from the authored-body word budget, so that adding refs never forces trimming of motion prose.
17. As the operator, I want the word-count floor applied to the remaining body after field drops, so that a heavily-referenced story is still forced to carry enough motion prose to animate.
18. As the operator, I want still spend recorded into the story's spend tally, so that the credit brake sees all paid calls, not just video renders.
19. As the operator, I want the released final command to carry the run's reference images as absolute paths, so that the staleness failure (final released without the validated refs) cannot recur.
20. As the operator, I want the probe-PASS hash computed over the compiled prompt plus the ordered reference list, so that swapping a reference invalidates a prior probe PASS instead of silently reusing it.
21. As the operator, I want the render ladder to be 480p probe → watch → native 1080p ×1 final, so that keepers are native-resolution generations, never upscaled probes.
22. As the operator, I want the upscaler documented as draft-salvage only, so that the blur failure class is closed by rule, not memory.
23. As the operator, I want a second 1080p take to require the existing logged override, so that re-roll spend is deliberate and visible, never a default.
24. As the operator, I want one final-tier log entry naming the kept take, so that re-rolls of a passed prompt don't pollute defect recurrence counts.
25. As the operator, I want the final command's sheet to carry a 720p fallback line for the case where 1080p with image refs is rejected, so that a known model limitation (n=1 evidence) has a pre-planned response instead of an improvised one.
26. As the operator, I want the per-story credit cap raised to 300 as a config value, so that the brake fits the 1080p-native ladder while still catching runaway spend.
27. As the operator, I want the first use of per-object stills explicitly judged for cross-object style coherence at the probe watch, so that this recipe variation (validated recipe used composed-still crops) earns its default status from a watched render.
28. As the operator, I want the composed-still + element-crop path documented as the fallback if per-object stills clash in style, so that a coherence failure has a proven recovery path.
29. As the operator, I want the next post produced through this stage end-to-end, so that the slice is validated by a real story rather than fixtures.

## Implementation Decisions

- **Declaration**: repeatable `--object <slug>` on the lane driver, parallel to `--character`; same slug rules and refs-directory convention. Objects are a third role class alongside `protagonist`/`in_frame`, with upload order characters-then-objects, declaration order within each.
- **Script schema**: the script artifact gains structured per-object world-element entries (slug + description) populated by the script seat from the declared list; scene/world prose for undeclared content is unchanged. The seat prompt change follows the lane's existing prompt conventions.
- **Asset generation module**: new module in the lane package; one function wraps the Higgsfield CLI image call (GPT Image 2) so tests fake it — the lane's existing fake pattern, not a new seam. Candidates land under the object's reference directory in a `candidates/` subdirectory; the gate ignores that subdirectory when validating promoted references. Halt reuses the slice ② request-sheet exception pattern with a pick sheet naming candidate paths and the promotion gesture.
- **Still prompt template**: data in the render-rules config (grammar-style row with evidence tag), not code constants — it is prompt content, expected to be tuned. Inputs: object description, shared style clause, vantage phrase derived from the script's scene field. Explicitly forbidden: any composed-target-frame content.
- **Compiler**: motion-only mode is triggered by presence of bound object refs; per-object description fields are dropped and replaced by one binding sentence each ("the X shown in imageN" convention, slice ② binding precedent). Binding sentences join the fixed-skeleton word-budget exemption. Word floor applies to the post-drop body. No-refs compile path byte-identical to today.
- **Hash**: probe-exemption hash input = compiled prompt text + ordered reference file names. Old log records simply never match new-format hashes — no migration.
- **Verdict/release**: final command derived from run-directory artifacts (compiled prompt + validated ref list) at release time; carries `--image-references` with absolute paths; resolution 1080p, one take. Second take = existing force/override flow (logged bypass). Final log entry notes kept take. Sheet includes the 720p fallback line (attempt 1080p first — failed jobs are uncharged).
- **Config changes** (render rules): ladder text (probe → watch → native 1080p ×1, upscaler = draft salvage only), per-story cap 150→300 (existing config value), still-cost row for the spend tally (GPT Image 2 ~7cr, measured 2026-07-22). Word-budget caps stay at the loosened experiment values; their revert decision is a separate pending operator verdict (probe A adherence), untouched here.
- **Spend tally**: still generations append spend records readable by the verdict flow's tally so the cap sees them; mechanism follows the lane's plain-files-per-run doctrine.
- **Product constants unchanged**: manual video rendering (operator pastes commands), 9:16, native audio, no on-screen text, Seedance 2.0 single-generation ≤15s, existing publish bookkeeping.

## Testing Decisions

- Good tests assert external behavior at the lane's two existing seams; no new seam classes, no implementation-detail assertions.
- **Seam 1 — driver level** (prior art: existing driver tests with fake LLM seats, fake Higgsfield runner, temp run/refs dirs). Asserts: declared object with empty refs halts with pick sheet BEFORE any LLM spend; cost line printed before generation; promoted keeper passes the gate on re-run; PASS verdict releases a final command containing the ref paths at 1080p; ref change after probe → prior PASS hash no longer exempts; still spend counts toward the 300cr cap; undeclared-object run behaves exactly as before (regression).
- **Seam 2 — pure functions** (prior art: existing compiler/asset-gate/verdict tests). Asserts: object arg parsing and slug validation; gate role rules incl. `candidates/` exclusion and loud invalid-dir failure; upload-order contract; still-prompt template output for a given description/style/vantage (deterministic, no composed-frame content); motion-only compile (field drop + single binding sentence per object, both-descriptions case impossible by construction); word-budget exemption and post-drop floor; hash stability and ref-sensitivity.
- Deliberately untested in CI: real GPT Image 2 calls, watch verdicts, Higgsfield billing, style-coherence judgment (operator watch is the instrument).

## Out of Scope

- LLM auto-detection of ref-worthy objects (operator declares; revisit only if manual flagging misses recurrently).
- Crop tooling / composed-still workflow automation (documented fallback path only).
- Video references, Seedance 2.5, multi-generation stories, >15s.
- A cross-story asset library beyond the existing per-slug refs directories (YAGNI until a repeat-topic story proves the need).
- Porting this stage to the scene/main lane (staged-director D2 for characters there is a separate slice).
- The word-budget revert/keep decision (pending probe-A adherence verdict — operator watch item, not build work).
- Posting automation; publish bookkeeping changes.
- The 1080p+image-refs capability question itself (attempt-first at release time answers it for free; this build only pre-plans the fallback).

## Further Notes

- Grilling session resolved: prose-strip mechanism (structured fields, not lexical matching), per-object stills vs composed+crop (per-object, first-use coherence gate, fallback documented), still-prompt authorship (template, no new seat), final-take verdict semantics (one entry, no per-take verdicts), ladder ×1 (operator override for re-rolls), cap 300 (operator declined the fork; AI call, brake-not-budget rationale).
- OpenMontage harvest check (pre-build): cost-governance estimate-before-spend and human-approval-gate patterns already mirrored here; its selector+provider tool registry is over-scale for one image model — not adapted. Re-check at done.
- Post #4 is this slice's live shakedown: first `--object` story runs the full flow; style-coherence watch item rides its probe verdict.
