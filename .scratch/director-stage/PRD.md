# Director stage — merge PLAN+SCENE, protect the story spine

Status: closed (superseded 2026-07-16 by staged-director-brain design; 01-03 shipped via `.scratch/staged-director-slice1` commit 7b54edc, 04's spine check rejected — see issues/04 comments)
Date: 2026-07-15
Design doc: `docs/superpowers/specs/2026-07-15-plan-fidelity-seam-design.md` (gitignored; this PRD is the durable record)

## Problem Statement

The user writes a story pitch, renders it, and watches a video in which the story did not happen.

Concretely, on pitch 47: the pitch says Elfaria drags Will **toward the bed**, then **lifts him onto the
bed** and cradles him. The rendered video cuts from Will being dragged straight to Will lying on her
chest. The bed is never seen. The lift never happens. The payoff shot opens at an end-state with no cause,
so it reads as incoherent — the user's words: the shots "don't flow, don't logically connect between cuts."

The cause is not the render model and not the picture quality (the frames look good). The prompt sent to
Seedance genuinely did not contain the bed or the lift. Two LLM stages rewrote the story between the
pitch and the prompt, and each rewrite silently lost facts:

| | pitch (`visual_line`) | PLAN (`motion_intent`) | SCENE (shipped) |
|---|---|---|---|
| shot 3 | "pulling him **toward the bed**" | "dragged backward **across the room**" | "dragged backward across the room" |
| shot 4 | "**lifts Will onto the bed** and cradles him" | "head lolling against Elfaria's chest" | "head lolling against ...'s chest" |

Verified from the Langfuse trace of the actual run, not inferred.

Nothing in the pipeline notices. The user's own diagnosis — "the SYSTEM PROMPTS are messing things up,
there is so much system prompts" — is correct: the prompts instruct decisions the schemas cannot carry,
so each stage re-decides in prose and the previous stage's answer is discarded.

This will not stay fixed by fixing pitch 47. Next month's pitch will lose a different fact, because the
mechanism — an unchecked paraphrase whose output is the only surviving representation — is general.

## Solution

**One director stage replaces two.** The director reads the story beat directly and writes the finished
Seedance prompt line. It is free to elevate the idea with craft — that is its job — but it may not drop
the story's spine, and code, not a prompt, enforces that.

From the user's perspective:

- The bed and the lift appear in the rendered video because they appear in the prompt.
- The pitch's framing (`shot_size`) is honored because code copies it, not because an LLM remembered to.
- A continuous physical move (lift-and-cradle) stays in one shot and is shown, rather than being cut
  across or reduced to its end-state.
- The pipeline has one prompt authoring the shot instead of two arguing about it.

**Governing frame (user, verbatim):** *"The pitch, in this case is the 'idea'. A director would then turn
that idea into something that is high quality which contains all sort of elements that creates a high
quality output."* The pitch is NOT ground truth to preserve verbatim. Adding "his arms stretching ahead,
three faint trails on the stone" is the director doing its job. Dropping "toward the bed" is not
elevation — it removes a documented required element. **Today nothing distinguishes those two edits.**
That distinction is the entire feature.

## User Stories

1. As a studio operator, I want the destination my pitch names ("the bed") to appear in the rendered video, so that the story's geography reads on screen.
2. As a studio operator, I want a required physical action my pitch names ("lifts him onto the bed") to be shown, so that the following shot has a visible cause.
3. As a studio operator, I want the writer to fail loudly when it drops a story fact, so that I learn before I spend credits, not after.
4. As a studio operator, I want the per-beat framing I chose (`shot_size`) honored exactly, so that my close-ups are close-ups and my wides are wides.
5. As a studio operator, I want a continuous move (reach→lift→clutch) rendered as one shot, so that the action does not get cut in half.
6. As a studio operator, I want the director to add craft (camera, sound, physical detail) my pitch did not specify, so that the output is better than my idea, not merely equal to it.
7. As a studio operator, I want one stage authoring each shot instead of two, so that a change to craft rules has one place to live.
8. As a studio operator, I want the director to see my actual pitch rather than another model's paraphrase of it, so that there is one place a fact can be lost instead of two.
9. As a studio operator, I want emotion written into the action as a physical change rather than as a stacked adjective, so that the payoff's register survives the render.
10. As a studio operator, I want to diff the shipped prompt against my pitch for free, so that I can validate the writer without spending a credit.
11. As a developer, I want the story spine enforced by a code assertion rather than a prompt instruction, so that the guarantee does not depend on LLM compliance.
12. As a developer, I want `shot_size` to have a schema field and a code copy, so that it stops surviving only as prose an LLM may ignore.
13. As a developer, I want the beat's spine expressed as structured fields, so that a check can be a deterministic assertion rather than fuzzy string matching.
14. As a developer, I want the writer's craft rules in one prompt, so that two prompts cannot disagree about the same decision.
15. As a developer, I want the "one action per beat" rule to mean one continuous move in both the pitcher and the director, so that relaxing it in one place does not relocate the bug.
16. As a developer, I want the Chinese translator removed, so that an untested premise stops sitting in the render path.
17. As a developer, I want tests that fail when a destination is dropped, so that this regression is caught by CI rather than by watching a video.
18. As a developer, I want the new tests to mirror the existing "copied from pitch not draft" tests, so that the codebase has one idiom for this class of guarantee.
19. As a maintainer, I want the reasoning and evidence recorded, so that a future session does not re-derive it from a video.
20. As a maintainer, I want rejected designs recorded with why, so that pass-through and expression-fields are not re-proposed.
21. As a maintainer, I want the corpus citation for each craft rule, so that rules can be re-checked when the model changes.
22. As a maintainer, I want out-of-scope defects logged rather than silently fixed, so that this change stays reviewable.

## Implementation Decisions

### D1 — SCENE stage is deleted; PLAN becomes the DIRECTOR (user decision)

The writer makes ONE LLM call per package instead of two. `motion_intent` ceases to exist — there is no
intermediate paraphrase. The director reads `beat.visual_line` directly and emits `scene_line`.

**SCENE's craft rules move into the director verbatim.** They are corpus-validated and are NOT the defect:
`SCENE_LINE_SYSTEM_PROMPT`'s structure (FRAMING → SUBJECT+ACTION → SPACE → CAMERA → AUDIO EVENT) already
matches the four-dimension per-shot scheme plus the 8-element formula's scene/environment element, with
style/quality/constraints correctly composed in code at the adapter. Filter-risk word substitution, the
word budget, the background clause, camera-speed variety, the timestamp ban, the stacked-move ban, and
name-exactness all survive. The stage dies; the knowledge does not.

**Rationale for merging:** two paraphrase hops meant two chances to drop a fact, and SCENE never saw the
pitch. Merging removes one hop. **This is a design bet, not corpus-validated** — the corpus documents
prompt products, not authoring pipelines, and has no opinion on one call vs. two.

**Cost accepted:** one prompt now does planning and Seedance prose. Instruction count does not drop; the
number of stages re-deciding the same thing drops from two to one. That is the intended win.

**The model-agnostic layer is abandoned** (PLAN was model-agnostic, SCENE was Seedance-native). The user
judged it speculative generality: the lane is locked to one Seedance generation and Kling is demoted to
nothing.

### D2 — The story spine is enforced by code, not by prompt (user decision)

Assert the beat's destination and required action appear in the shipped `scene_line`; fail or repair when
absent.

**Why not a prompt rule:** the failure was prompt *adherence*. PLAN was told "ONE subject action", obeyed,
and obeying is what dropped the lift. Adding "...but never drop a destination" puts two instructions in
direct tension and lets the LLM referee — the exact failure mode being eliminated. A prompt is what failed;
only code guarantees the property.

**This mirrors an existing, deliberate pattern.** `beat_role`, `characters_in_frame`, `dialogue_line`, and
`speaker` are already code-copied from the beat under the comment *"code copies the pitch's own beat facts
... rather than trusting the draft's echo of them."* The story is the one beat fact that never got that
treatment. D2 extends the existing principle rather than inventing a mechanism.

### D3 — `StoryBeat` gains structured spine fields (user decision)

`destination: str | None` and `required_action: str`, alongside the existing prose `visual_line`.

Prose cannot be checked deterministically — extracting "the bed" from *"...pulling him toward the bed"*
needs NLP or an LLM judge, and an LLM judge is the thing D2 rejects. The fields make the check a
substring assertion.

`destination` is nullable: not every story has one. The check fires only when it is set.

**Corpus is silent here** — every framework governs clause order inside a prose line, never JSON shape.
This is a verifiability engineering call, explicitly not a prompt-anatomy question.

**Accepted cost:** the pitcher states the destination twice (in prose and as a field), and duplication can
disagree with itself.

### D4 — "One action" is re-scoped to ONE CONTINUOUS MOVE, in both places (user decision)

A continuous move is one action however many sub-motions it takes. Lift-and-cradle is one shot.

**This was blocking, not cosmetic.** With a singular `required_action` and the old rule, the pitcher would
have to pick `lifts` OR `cradles` for beat 4 — the check would protect one and let the other vanish,
baking the bug into the schema.

**The conflict:** the pitcher currently forbids "three micro-motions crammed into one beat — split them
across beats." Against it, `ai_video_resources/Dan Kieft Cinematic Seedance Updated.md:471`, verbatim:

> **One flowing motion per shot.** Write "he speaks and immediately whips his head around in panic" as
> one continuous action, not a setup sentence + an "after he finishes…" block (that reads as two shots).

Reach-lift-clutch is literally three micro-motions by our rule. Since every beat becomes a cut, our finer
grain **manufactures cuts in the middle of continuous actions** — which L471 says reads as two shots.

**Cite L471 and only L471.** An earlier draft of this PRD cited "Dan Kieft:51,471" and said the corpus
"warns never to let a continuous physical action span an unshown gap." Both were wrong, and the error is
worth recording because the conclusion happened to survive it:

- **L51 is a different rule** — a 6-SHOT CEILING: "if over 6, merge actions into fewer shots. Multiple
  small actions go in ONE shot: 'reaches in → lifts egg → clutches it → backs away' is ONE shot, not
  four." That is shot ECONOMY, not continuity. Same conclusion, different mechanism. Citing it here
  overstated the corpus's support. (Its sibling `:469` is economy too.)
- **"span an unshown gap" is not L471's claim.** L471's stated reason is that splitting a flowing move
  *reads as two shots* — about prose structure, not about the audience missing the action.

**[inference] Source-tier caveat.** L471 lives in the OpenArt-frontend playbook that `INDEX.md` flags
"cherry-pick claims, never adopt wholesale" — the same file whose Chinese-prompt rule this project
rejected and deleted on the same day (ticket 01). Cherry-picking L471 is defensible where that was not:
it gives its reason, and it concerns prose structure rather than frontend mechanics, so it plausibly
transfers to the Higgsfield CLI. **Plausibly, not measured** — nothing in the corpus tests it on our
platform. If a future render shows flowing-motion beats rendering worse, this is the assumption to pull.

**SUPERSEDED 2026-07-15 (during ticket 03) — the caveat above understates D4's footing. Read this
before pulling the assumption.** [cited] A second, independent corpus source says the same thing, and
it is the source the project's own `config/render_rules.yaml` ALREADY cited for this very rule:
`ai_video_resources/image-video-director/03-video-prompting-techniques.md:14` — *"Constrain each shot to
a single camera behavior and a single subject action"* — whose own worked example at `:16` is:

> Example: "Actor takes four steps to the window, pauses, and pulls the curtain in the final second."

**Three sub-motions and a destination, and the corpus calls it ONE subject action.** So "one subject
action" NEVER meant one verb, anywhere in the corpus. D4 is not a departure from the corpus — it is a
**restoration** of it. 03 is a general video-prompting doc, NOT the flagged OpenArt playbook, so the
source-tier caveat does not apply to it.

**This also re-dates the root cause.** The bug was not that our rule disagreed with the corpus; it was
that our rule COMPRESSED the corpus rule down to the bare phrase "ONE subject action per shot" and
dropped the example that defined it. The bare phrase is what PLAN echoed and what the LLM obeyed when
it collapsed "lifts... and cradles" to "cradles". A rule stripped of its example silently changes
meaning — the same mechanism as [[feedback_prompt_examples_far_domain]]'s no-examples ablation (0/5
fields filled), hit from the other direction.

**The conflict with our pitcher's "split micro-motions across beats" rule stands as described above** —
that rule is genuinely ours and genuinely wrong, and 02 relaxed it. Nothing here changes that.

**The evidence:** the user watched the render. It cuts from dragging straight to lying-on-chest. Beat 4
("lifts Will onto the bed and cradles him") **violated our rule and was correct for it**; the craft gate
passed it anyway; then PLAN's `ONE subject action` collapsed it to one verb and killed the lift.

The rule must change in BOTH the pitcher and the director. Relaxing one relocates the failure.

### D5 — `shot_size` gets a schema field and is code-copied

It has no field in the draft or the package today, so it survives only as prose the LLM may or may not
honor. Copy it from the beat exactly as `beat_role` is copied.

### D6 — The Chinese translator is deleted

The "write in Chinese, never English" rule traces to a practitioner doc for the **OpenArt** frontend — not
Higgsfield — with no justification given anywhere in its 598 lines, and the repo's own INDEX flags that
file "cherry-pick claims, never adopt wholesale." The only source matched to both Higgsfield **and**
Seedance reports English phrasings transfer near-directly. Genuine Chinese-fidelity claims exist but are
for Kling and Jimeng — different models. The project's own translation spec admits the premise: *"trust
that Chinese wins, no pre-A/B."*

**Correction on the record:** the stage is NOT broken-and-silently-failing. It has a designed 5-check
graceful fallback. A real substring bug exists in dialogue validation, but it is moot once the stage goes.
This is deleting an unvalidated premise, not fixing a bug.

### D7 — Expression is a prompt rule, NOT a field

Folded into the action clause as physical detail; close-up/climax only; phrased as a CHANGE ("expression
softens"), never a static adjective stacked on every shot.

A full read of 117 corpus prompts found expression words in ~9% of shots, always change-driven, always
clustered at close-ups. Every Seedance formula folds emotion into Action — none has a standalone slot.

**The render corroborates.** Pitch 47's payoff asked for "a cool, satisfied smirk" — a static adjective
stack — and rendered as a soft, tender smile. The register inverted on the one shot the whole pitch drives
toward. That is the documented weak form failing in practice.

**Known unresolved risk:** the corpus separately and emphatically requires reference-sheet faces to be
neutral/expressionless to avoid "midpoint face" blending. Writing an expression *change* while the attached
ref face is neutral is a potential prompt-reference fight that **no source reconciles.** We ship into that
gap knowingly.

### D8 — Lighting is NOT touched

The current split is already corpus-correct: the SPACE clause names the physical light SOURCE that changes
shot to shot, while `world_anchor` describes nothing about how the room looks. That matches the documented
rule — describe the CHANGE, not the static content the reference already carries. The "don't describe after
uploading a ref" rule is scoped narrowly to character *appearance*; its own template still carries a
lighting field with an environment ref attached, and the 8-element worked example states lighting alongside
an attached room photo.

### D2/D3 ARE REJECTED — the lexical spine check was disproven on real output (2026-07-15, user call)

**Do not re-propose the substring/overlap check. It was built, measured, and it does not work.**

D2 ("assert the destination and required_action appear in the shipped scene_line") and D3 ("the fields
make the check a substring assertion") both assume the spine fields are STABLE, CHECKABLE TOKENS. They
are not. Measured on real director output from pitches 50 and 51:

| the pitcher's `destination` for the SAME payoff beat | vs pitch 47's real bug line | vs real good output |
|---|---|---|
| `"the bed"` (chosen on pitch 48) | FAIL — catches it | PASS |
| `"Elfaria's chest"` (chosen on pitches 50 AND 51) | **PASS — misses the bug** | **FAIL — false-fails good writing** |

The check's correctness is a coin flip on which noun the pitcher happened to pick. Worse, the two failure
modes are exactly inverted: pitch 47's real bug line is *"head lolling against Elfaria's chest"* — it
CONTAINS "chest", so the check passes the bug it was built for; meanwhile the good line says "cradling
him; his head lolls against her **shoulder**", so the check fails correct output.

`required_action` overlap fares no better: the clean-spine positive floor measured **0.62** against a real
bug at 0.42 — a +0.03 margin over any usable threshold, with beat 1 "missing" `grasp/halt/reach` only
because the director wrote "grips his wrist".

**The root cause is not tunable.** The director is REQUIRED to paraphrase — that is the elevation this
PRD exists to protect ("Adding 'his arms stretching ahead...' is the director doing its job"). Synonym
substitution (chest→shoulder, grasping→grips) is indistinguishable, lexically, from dropping a fact. A
deterministic word check cannot separate the two, because both look like *different words*. Only meaning
separates them, and reading meaning is the LLM judge D2 explicitly rejects. **D2's own reasoning
("only code guarantees the property") is sound about prompts and wrong about this property: some
properties are not code-checkable at all.**

**What replaced it (user decision, 2026-07-15): nothing, and that is the honest answer.** The bug does
not reproduce. Two live runs post-02/03 (pitches 50 and 51) both shipped the bed AND the lift. Tickets 02
(structured spine in the pitch) and 03 (one director reading the beat directly) fixed it. Building an
unreliable alarm for a break-in that stopped happening costs real things: it blocks good output, and its
repair loop would nag the director toward specific words, fighting the craft rules 02/03 just established.

**The guard that IS sound** is structural, not lexical:
`test_director_sees_each_beats_own_story_not_a_paraphrase` pins that the director receives each beat's
own visual_line/destination/required_action with no stage in between. Reintroduce a paraphrase hop and it
fails. It cannot pin that the LLM honors what it reads — that is evidenced by live runs, not unit tests.

**Accepted cost, stated plainly:** if this failure class returns in a new form, nothing catches it
automatically. It gets caught the way it was caught the first time — by watching the render. That was
expensive, and it is the price of not having a check that works.

**D5 (`shot_size` gets a field and is code-copied) is dropped with it, for a different reason.** Grep of
`src/`: `shot_size` exists ONLY in `StoryBeat`, its variety validator, and prompt prose. Nothing in
`src/schemas/generation.py`, the adapter, or the executor reads it. Framing reaches the model solely as
prose inside `scene_line`. So code-copying it into `ShotSpec` would add a field no consumer reads — dead
metadata — and the only way to make it *do* anything is to validate `scene_line`'s framing prose against
the enum, which is the same lexical disease ("Medium shot" vs `medium`). The beat's shot_size still
governs via the director prompt's FRAMING clause, which is where it was always actually enforced.

### Rejected designs (recorded so they are not re-proposed)

- **Pass-through** (freeze `visual_line`; director only adds camera+sound). Contradicts the governing frame —
  it would freeze the idea and ban the craft. Also removed only one of two paraphrase hops, so it never
  killed the failure class it claimed to.
- **An `expression` field.** See D7.
- **A `lighting` field.** See D8 — would duplicate `world_anchor`'s job.
- **`end_state` motion-carry across cuts.** The corpus says end on a cut and start a new scene; do not
  expect motion to carry. State may carry; motion may not.
- **A "director agent" that decides everything and asks for clarification when unsure** (the user's original
  proposal). No precedent in this codebase or in OpenMontage that is not synchronous-human-shaped; this
  pipeline runs unattended. What survives of the idea is this PRD: one stage owning the craft, bound to
  preserve the spine.

## Testing Decisions

**What makes a good test here:** assert on the package the writer returns — the shipped `scene_line` and
the copied beat facts. Never assert on prompt text, call counts, or intermediate structures. The guarantee
is "the story reached the prompt," and that is externally observable at the writer's boundary.

**Seam: one, and it already exists.** `ContentWriter.write(pitch, llm, rules) → MultiShotPackage`, with a
`FakeLLM` returning queued structured outputs by response-model type. No new seams. The merge to one LLM
call *simplifies* this seam — `FakeLLM` no longer needs to answer two different response models.

**Prior art, and it is exactly this principle:** `tests/generation/test_content_writer.py` already contains
`test_beat_role_and_cast_copied_from_pitch_not_draft`, `test_dialogue_and_speaker_copied_from_pitch_not_draft`,
and `test_silent_beat_stays_silent_even_if_draft_invents_narration`. Each hands the FakeLLM a draft that
contradicts the pitch and asserts the pitch wins. The new tests are direct mirrors for the story spine.

**Modules tested:**
- `ContentWriter` (`tests/generation/test_content_writer.py`) — the spine check, `shot_size` copying,
  the single-call flow.
- `StoryBeat` / `StoryPitch` schemas (`tests/monitor/test_monitor_schemas.py`, `test_schemas.py`) — the new
  spine fields and their nullability rule.
- `StoryPitcher` (`tests/monitor/test_story_pitcher.py`) — the re-scoped continuous-move rule.
- `test_prompt_translation.py` is **deleted** with the stage.

**Tests to add:**
1. A director line that drops the beat's `destination` raises (or repairs) — the pitch-47 regression, stated as a test.
2. A director line that drops the beat's `required_action` raises (or repairs) — the missing lift.
3. `shot_size` is copied from the beat even when the draft echoes a different one — mirrors `test_beat_role_and_cast_copied_from_pitch_not_draft`.
4. A beat with `destination: None` skips the check and does not raise.
5. A director line containing destination and action passes untouched, and craft additions absent from the pitch are preserved (elevation is not clipped).
6. Existing craft-rule tests (word budget, retry-once-with-feedback) still pass against the merged call.

## Out of Scope

- **Pacing.** No lever exists in the single-generation lane: `duration` reaches Seedance once for the whole
  generation, the per-shot field is a word budget, bracketed timestamps are measured-rejected on the
  Higgsfield CLI, and word-count↔screen-time correlation is absent from the entire corpus. Pacing needs the
  splice lane. **This work must not be judged on pacing.**
- **Lane change (single generation → per-scene splice).** The corpus's one lane rule is keyed to content
  type — long-take for dialogue/emotional scenes, splice for action/montage — and says real production
  combines both. Pitch 47 is action, so the rule leans splice for this story. Deferred until a clean render
  exists.
- **Motion quality.** Unknown. A still cannot show it and the render has not been assessed for it. This is
  the one symptom that could indict the lane rather than the pipeline.
- **Turnaround-sheet references.** Vendor troubleshooting says multi-view refs read as multiple subjects and
  worsen ID drift; we send 4 refs/character including a turnaround sheet. Real, survived adversarial
  verification, never reconciled in the corpus. It targets identity drift, which the user did **not** report.
  **Must be fixed before any validation render or the render is confounded** — as every render so far has been.
- **The latent voiceover path.** The PLAN prompt still instructs narration composition (its `hook_text`
  sibling was updated to "ignore"; this one never was), and assembly still calls TTS and mixes it whenever
  `narration_line` is non-null, with no global kill-switch — only the convention that the pitcher emits null.
  A stale pre-pivot pitch row would ship real voiceover into a no-voiceover product. Log and fix separately;
  do not carry `narration_line` into the director unexamined.
- **`motion_tag` and `duration_seconds`.** Both absent from every corpus framework. `motion_tag` is
  project-invented ML metadata; `duration_seconds` gates a total-duration validator. Keep on pipeline
  grounds, not craft grounds. Not re-litigated here.

## Further Notes

**Validation is two steps and they answer different questions. Do not conflate them.**

1. **FREE — this validates the work.** Re-run the writer on pitch 47, zero credits. Diff the shipped
   `scene_line` against `beat.visual_line`. **Pass = the bed and the lift survive.** That is the entire
   success criterion for this PRD.
2. **PAID — a separate, conscious go/no-go.** One render answers a *different* question: does story
   coherence alone move the needle? This work does not touch pacing or motion — two of the user's three
   reported symptoms. If the render still reads slideshow-y, that does **not** mean this failed; it means
   the lane/model ceiling is real and the splice fork is live. Fix the refs first.

**The free diff is necessary but not sufficient.** In pitch 47, "she looks down with a cool, satisfied
smirk" **was** in the shipped prompt and the render still inverted its register. Getting the words right
does not guarantee the picture. The diff proves the prompt; only a render proves the screen.

**Evidence quality note.** Every render to date is confounded by the turnaround-sheet defect, so no clean
data point exists about the lane. The one prior splice comparison is likewise confounded and its own author
flagged it "COUNTER-EVIDENCE... NOT yet a supersession — pending fresh-pitch validation." Treat all
existing lane evidence as unusable until a compliant render exists.

**Process note for whoever picks this up.** The root cause was found by reading the Langfuse trace of the
actual run — not by reasoning about the code. Several confident hypotheses (that a "never describe the
location" instruction stripped the bed; that per-shot duration was a pacing lever; that ID drift explained
pose resets) were disproven by primary evidence after being asserted. When this pipeline surprises you,
read the trace first.
