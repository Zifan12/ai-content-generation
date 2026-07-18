# PRD: POV Pipeline — slice ② (canon-IP subjects)

Status: draft — awaiting operator review
Date: 2026-07-18
Evidence base: `RESEARCH-slice2.md` (6-thread corpus sweep + repo-measured facts, 2026-07-18, all claims file:line-cited). Grilling session 2026-07-18 resolved the five product forks; decisions below are operator-ratified.
Predecessor: `PRD.md` (slice ①, shipped 2026-07-17 — generic invented worlds, text-only). This slice adds recognizable canon subjects; it changes nothing about slice ①'s register, grammar locks, or artifacts.

## Problem Statement

The shipped POV pipeline can only render INVENTED subjects. Any story naming a canon design — a specific hero's suit on your own arms, a specific character standing in front of you — needs that design matched exactly, and text cannot hold exactness (six documented hallucination mechanisms; asset routing rule 2026-07-17: EXACTNESS axis → reference image required). There is currently no reference path in the POV lane at all: no way to declare a canon subject, no rules for what images the model needs, no compiler support for binding references into the prompt, and a verified filter-safety gap (the POV scrub never applies the action-word substitution table, so any combat payoff risks a content-filter kill). Canon-IP content — the recognition hook the account thesis rides on — is unreachable until this exists.

This is a CLASS problem, not a story problem. Every mechanic below serves a recurring content class; the operator's current story ("POV: you are Ultraman, fire the spacium beam") is only the first validation instance. No code artifact may contain an example-specific string.

## Content classes served

| Class | Mechanic | Status after slice ② |
|---|---|---|
| Protagonist-as-IP (your limbs wear a canon design) | limb/costume ref crops + POV binding clause | probe-validated, pipeline-supported |
| Canon character in frame (you see them) | mask/head + full-body refs, speaks-into-lens craft | pipeline-supported, probe deferred to first real story |
| Energy/beam attack payoff (any IP) | kinetic beam vocabulary + action-wrap scrub | probe-validated |
| On-camera transformation (henshin) | unknown — zero corpus precedent, flash-mask needs a cut our grammar bans | OUT OF SCOPE, own probe later |

## Operator-ratified decisions (grill 2026-07-18)

1. **v1 stories start already-transformed.** The transformation moment is deferred to its own probe; it is the single riskiest unproven mechanic (no POV+transformation example exists anywhere; the corpus's only masking technique requires a shot cut that the locked POV grammar forbids).
2. **Protagonist-as-IP references = crops of what the camera sees** (suit arms, gloves, costume detail) — no face/mask panel, no full-body sheet. Rationale: the ref should contain exactly what may appear on screen; a full-body ref of a character the grammar declares unseen risks summoning them as a separate in-frame figure. Corpus supports crops-as-refs as third-person practice (`reference-material-playbook.md:178`) but has zero POV-protagonist example — hence probe. Escalation pre-registered: if roll 1 fails to bind, roll a full-sheet variant against it (A/B).
3. **Canon-character-in-frame is code-supported from day 1, probe-deferred.** The asset gate and request sheet handle the role generically; no credit is spent on its register until a picked story needs it.
4. **Probe round cap: 120cr** (30cr per 480p/10s roll, reroll-and-select policy 2-3 rolls, remainder = escalation buffer). Failed/rejected jobs refund. Stop at cap and report.
5. **Reference source = ONE version's clean official art**, operator-picked at sourcing time. Version consistency matters more than version choice: refs and prompt must agree on a single design or the averaging failure fires.

## Solution

Same driver, same artifacts, one new gate and three touched components.

```
pov.py --idea "..." --character <slug>[:role] [--character <slug>[:role] ...]
  → asset gate [NEW]
  → pitcher / script writer (touched: ref-aware craft rule)
  → compiler (touched: binding clause + action-wrap scrub)
  → render sheet (touched: --image flags + ref watch checklist)
```

**Asset gate** (`src/generation/pov/asset_check.py`, deterministic code): for each declared character, look for `refs/<slug>/`. Missing or invalid → print a REQUEST SHEET and halt. The request sheet is role-specific:
- role `protagonist`: 2-4 crops of what the camera will see — suit forearms/gloves front + ¾, costume detail crop (emblem/chest) if the design has one. No face, no full body.
- role `in-frame`: mask/head close-up (the ONE identity-bearing panel), full-body front; per the one-face-region rule.
- Both: non-photographic official art only (settei > key art > renders; never live-action screencaps — quality tier AND BUG-012 NSFW risk), neutral expression where applicable, one design version throughout, ≤9 image refs total per render (hard CLI cap).
Validation = code checks only: file count within role bounds, image files readable, slug matches a declared character. No LLM judge (house rule: none until a real failure proves code checks blind). Operator drops files, reruns, gate passes → keepers are the permanent library for that character; repeat subjects are cache hits.

**Script writer** (touched): declared characters arrive with `ref_bound: true`; new craft rule — ref-bound subjects are role-named only, appearance prose FORBIDDEN (appearance is owned by the image; re-describing it was BUG-021's defect class). Enforced like existing craft rules: structural check + one bounded repair.

**Compiler** (touched, still deterministic code):
- Binding block composed by code, positional convention: protagonist role → one clause binding the visible limbs to `(image1..N)`; in-frame role → the existing scene-lane sentence shape ("X is the character shown in imageN"). Exact protagonist wording is decided by the probe, then frozen verbatim in config like every other skeleton clause.
- Action-wrap scrub [gap-close]: apply the sensitive-word substitution table (`kill/attack → dramatic energy clash` etc., already in `render_rules.yaml` scene_lane dialect) to POV output. Today `_scrub()` reads only the three kill-list families — verified gap, must close before any combat beat compiles.
- Beam/energy vocabulary: kinetic verbs (crackle, arc, surge, erupt, discharge) — never glow/glimmer routing; the existing glow substitution was tuned for static objects, wrong tool for attack beams.
- Caps enforced: ≤3200 prompt chars, ≤9 image refs, ≤12 reference files.

**Render sheet** (touched): CLI command carries one `--image <path>` per keeper ref (CLI auto-uploads; refs add ZERO credit cost — billing is seconds × resolution only, measured). Watch checklist gains ref-specific failure modes: identity/costume mismatch vs source art, costume detail drift, style bleed from ref into world, duplicate-figure (twins), protagonist-summoned-into-frame (the class-specific failure this slice invents a check for).

**Config** (`render_rules.yaml` `pov_grammar`): every probe-validated rule lands as an evidence-tagged row (probe artifact path or corpus file:line), same discipline as slice ①. Known defect to fix on probe evidence: `style_register`'s "No 3D, no cartoon, no VFX aesthetic" negation was bolted on from an anti-plastic-skin fix and directly fights beam-VFX beats; probe A tells us whether to scope it.

## Build order (probe-first — no pipeline code before probe evidence)

1. **Probe A** (hand-built, no code): protagonist-as-IP + beam payoff on the slice-① skeleton. Hand-sourced crops per decision 2, hand-written binding clause candidates. 480p/10s, ≤120cr, reroll-and-select, operator watches (no sampled-frame verdicts). Answers, per class: (a) do crops bind to the POV camera-holder's limbs; (b) does costume hold without a start-frame anchor; (c) does a beam render at all in POV register (zero watched evidence exists anywhere); (d) does the action-wrapped phrasing survive the filter.
2. **Config rows** from probe results, evidence-tagged.
3. **Code slice**: asset gate + script-writer rule + compiler changes + render-sheet changes, tests at the two established seams (driver-with-fake-seats, compiler-as-pure-function), plus asset-gate tests (request-sheet emission, validation pass/fail).
4. **Validation run** = the operator's next post (first instance of the protagonist-as-IP class), through the pipeline end to end.

## Testing decisions

Same two seams as slice ① (no implementation-detail assertions):
- Driver seam: declared character without refs → request sheet emitted + halt; with valid refs → run proceeds and ref paths appear in the render sheet verbatim (code-copy proof); invalid ref dir (bad count, unknown slug) → named validation error.
- Compiler seam: binding clause present verbatim per role; appearance prose absent for ref-bound characters; action-wrap substitutions applied; kill-list still enforced; caps respected; `--image` flags match keeper paths in order.
- Probe outcomes, watch verdicts, and filter behavior are manual gates by design — untested in CI.

## Out of scope

- Transformation/henshin mechanic (own probe, own decision round).
- Canon-character-in-frame PROBE (code support ships; register validation waits for a real story).
- Automated reference sourcing/web-fetch, reference generation, style pre-conversion tooling (pre-convert only if a watch shows style bleed; then it is one manual image-gen step, not machinery).
- LLM judge of reference quality.
- V2V techniques (different render mode, never attempted on this stack).
- Multi-generation/splice, DB persistence, Seedance 2.5 — unchanged from slice ①.

## Open items

- Exact protagonist binding-clause wording — probe A decides, then frozen.
- `style_register` VFX-negation scoping — probe A evidence.
- Whether the money-shot contract needs a ref-aware variant for beam payoffs (slice ①'s contract explicitly excludes IP topics) — revisit at code slice with probe evidence in hand.
