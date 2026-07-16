# 03 — One director stage replaces PLAN and SCENE

**What to build:** The writer makes ONE LLM call per package instead of two. The director reads each story
beat **directly** and writes the finished Seedance prose line for it. The intermediate `motion_intent`
paraphrase ceases to exist.

Today the chain is: beat → PLAN rewrites it into `motion_intent` → SCENE rewrites *that* into `scene_line`.
SCENE never sees the pitch. Two rewrites, two chances to lose a fact, and the trace of the pitch-47 run
shows exactly that happening — PLAN turned "pulling him toward the bed" into "dragged backward across the
room", and SCENE faithfully copied the loss. After this ticket there is one rewrite, and it reads the real
beat.

**SCENE's craft rules move into the director verbatim — they are not the defect.** SCENE's structure
(FRAMING → SUBJECT+ACTION → SPACE → CAMERA → AUDIO EVENT) already matches the corpus's four-dimension
per-shot scheme plus the 8-element formula's scene/environment element, with style/quality/constraints
correctly composed in code at the adapter. A corpus sweep's verdict: *"this part of the current
architecture is not what needs fixing."* Filter-risk word substitution, the word budget, the background
clause, camera-speed variety, the timestamp ban, the stacked-move ban, and name-exactness all survive.
**The stage dies; the knowledge does not.**

**Two rules change on the way in:**

1. **The continuous-move grain (pairs with 02).** The director's "ONE camera move + ONE subject action"
   must mean one *continuous move*, not one verb. This rule is what collapsed "lifts... and cradles" down
   to "cradles" and killed the lift. Relaxing it in the pitcher (02) but not here just relocates the bug.
2. **Expression is folded into the action, never a field.** Close-up/climax only, phrased as a CHANGE
   ("expression softens"), never a static adjective stacked on every shot. A read of 117 corpus prompts
   found expression words in ~9% of shots, always change-driven. Pitch 47's payoff asked for "a cool,
   satisfied smirk" — a static adjective stack — and rendered as a soft tender smile: the register
   inverted on the one shot the whole pitch drives toward.

**Known unresolved risk, ship knowingly:** the corpus separately insists reference-sheet faces be
neutral/expressionless to avoid "midpoint face" blending. Writing an expression *change* while the attached
ref face is neutral is a potential prompt-reference fight that no source reconciles.

**Honest framing:** merging is a design bet, **not** corpus-validated. The corpus documents prompt products,
not authoring pipelines, and has no opinion on one call vs. two. The bet is that one hop drops fewer facts
than two. The cost is that one prompt now does planning and Seedance prose, and may do both slightly worse
than two specialists did.

**Blocked by:** None — can start immediately. (Recommended after 01 to shrink what's in play, but the
translator sits at the adapter and never touches the writer, so it does not gate this.)

**Status:** done (2026-07-15)

- [x] The writer makes exactly one LLM call per package; the fake LLM in tests no longer needs to answer two response models.
- [x] `motion_intent` no longer exists in any schema or prompt.
- [x] The director receives each beat's own `visual_line` — not a paraphrase — and emits `scene_line`.
- [x] Every craft rule that lived in the SCENE prompt is present in the director prompt and still enforced.
- [x] The director's action rule permits one continuous move spanning several sub-motions.
- [x] The director prompt instructs expression as a folded-in change at close-ups, and does not add an expression field.
- [x] The package shape reaching the adapter is unchanged — this ticket is invisible downstream.
- [x] Existing writer tests (word budget, retry-once-with-feedback, beat-count mismatch, silent-beat) pass against the merged call, adapted only where they named the deleted stage.
- [x] The model-agnostic split is gone; nothing pretends the plan layer is render-model-neutral.
- [x] `uv run pytest`, `uv run ruff check .`, `uv run mypy src/` all pass.

**Implementation notes (2026-07-15).**

- Schemas renamed on the user's call: `ShotDraft` -> `DirectorShotDraft`, `ShotPlanDraft` ->
  `DirectorDraft`, field `motion_intent` -> `scene_line`. "Plan" named a stage that no longer exists.
- `SceneLines` is deleted. A line-count mismatch was its own failure mode (and its own test) because a
  second call could return N lines for M shots; with `scene_line` a per-shot FIELD, structured output
  makes one-line-per-shot structural. The only count that can still be wrong is shots-vs-beats.
  `test_scene_line_count_mismatch_raises` was deleted rather than adapted.
- The injection guard survived the merge but changed tag: `<plan>` -> `<story>`. The pitch (untrusted
  data) rides inside; the motion craft and `world_anchor` blocks stay OUTSIDE, because `world_anchor`
  is an instruction to OBEY ("describe NOTHING about how it looks") and a treat-as-data wrapper would
  disarm it. Pinned by `test_pitch_travels_inside_the_injection_guard`.
- The old scene envelope hand-copied the dialogue pair out of the source beat because it never saw the
  pitch. That copy site is gone — the director reads the beat's dialogue natively.
- **`narration_line` was examined, not carried unexamined** (PRD required this). PLAN's narration-
  composition rule ("2.2 words per second") is dead weight: the pitcher's own prompt retires the field
  ("LEAVE THIS NULL"), and the writer's gate (`draft.narration_line if beat.narration_line is not None
  else None`) drops the director's narration on the live path regardless. Replaced with `hook_text`'s
  "ignore — always return null" one-liner. Live-path behavior is byte-identical; a legacy row is
  strictly safer. The assembly-side TTS kill-switch remains out of scope — logged as **BUG-029**.
- One conflict the merge forced into the open: SCENE said "never repeat the previous shot's framing",
  but the beat's `shot_size` is authoritative (and 04 code-copies it). Resolved rather than asserting
  both — shot_size is authoritative, and the ANGLE (which shot_size leaves open) carries the variety,
  per Dan Kieft:470's 30° rule.
- `duration_seconds`' justification was stale (it cited narration budgets, which no longer exist). Now
  states what it actually gates: the product's total-runtime envelope validator.

**Adversarial diff of the merged prompt (commit `09cda94`) — 4 real defects, all fixed.** The merge
landed green in `a3270fb`; an adversarial agent then diffed the merged prompt clause-by-clause against
the two it replaced. Rule survival came back clean (all seven named survivors byte-for-byte verbatim;
D4 and D7 verified sound; the injection guard is actually a net HARDENING, since the old PLAN call
wrapped the raw pitch JSON in no guard at all). But it found four things worth recording:

1. **The far-domain rule was broken by the prompt that documents it.** The role block illustrated a
   dropped destination with "dragged backward across the room", and D7 illustrated a static adjective
   with "a cool, satisfied smirk" — both lifted VERBATIM from pitch 47's real shipped output, and both
   sitting directly under a comment asserting every example below was far-domain. **The lesson worth
   keeping: a NEGATIVE example still teaches the model the vocabulary it is being warned about.**
   Cautionary examples need the far domain exactly as much as positive ones. Now a lighthouse/headland
   pair and "a fierce, determined glare".
2. **The prompt claimed a code guarantee that does not exist.** FRAMING said shot_size is authoritative
   "and the system re-copies it regardless" — nothing copies it; `ShotSpec` has no `shot_size` field
   until 04 adds one. Beyond being untrue, "regardless" actively signalled to the model that getting it
   wrong is free. Softened to a claim true today; 04 can strengthen it once the copy exists.
3. **PLAN's arc-allocation rule was dropped unintentionally** (not one of the two pre-cleared
   deletions). Restored — minus its framing half ("wide early, closest at the payoff"), which would now
   contradict shot_size being the beat's to choose. That narrowing is deliberate and is recorded in the
   prompt header rather than left silent.
4. **"Show emotion ONLY through the body" lost its "only"** to make room for D7's close-up exception.
   Judged fine (the exception is tightly scoped) but recorded, since the ticket's claim is "verbatim".

Also inherited, NOT fixed: the SPACE clause's "a bedside lamp" light-source example predates this work
and mildly resembles the project's real bedroom location. Untouched by the merge, so not a regression —
noted for whoever next revises this prompt.

**D4 was only half-done until commit `978df85` — the injected YAML still carried the rule D4 replaces.**
The director's EFFECTIVE prompt is `DIRECTOR_SYSTEM_PROMPT` **plus** the `motion_craft` block that
`_build_director_envelope` injects from `config/render_rules.yaml`. The merge put ONE CONTINUOUS MOVE in
the system string while the YAML still shipped `one_move_one_action: "ONE camera move + ONE subject
action per shot"` — the exact phrasing that collapsed the lift. The director was handed D4 AND the rule
D4 replaces, and left to referee: the failure mode D4 exists to kill, relocated from the prompt into the
data. The prompt audit could not catch it — it read the string, not the block. **Whoever edits a system
prompt in this repo next: check what the envelope injects, not just the constant you edited.** Pinned by
`test_injected_motion_craft_does_not_contradict_the_continuous_move_rule`.

That fix turned up the session's most useful finding, recorded in full at PRD §D4: the corpus source
`render_rules.yaml` already cited for this rule (`image-video-director/03:14,16`) calls *"four steps to
the window, pauses, and pulls the curtain in the final second"* — three sub-motions plus a destination —
**ONE subject action**. D4 is a restoration of the corpus, not a departure from it, and it now rests on a
second source outside the doc INDEX.md flags "never adopt wholesale". The root cause re-dates to a rule
COMPRESSED away from its defining example, not a rule that disagreed with the corpus.

**What this ticket did NOT do.** It merged the stages; it did not fix pitch 47. Nothing yet asserts the
bed or the lift survive — that check is 04. Report honestly: merged, green, downstream shape unchanged.

**Pre-existing failure found, not caused here:** `test_package_total_10s_accepted` builds a 2s shot
against a floor raised 2->3 on 2026-07-12. Confirmed pre-existing by stashing this diff and re-running
on HEAD. Logged as **BUG-028** (the 10s envelope floor is currently untested — the test dies in its
fixture). `tests/rag/test_rag_retriever.py::test_latency` is the known flaky one. Ruff's repo baseline
is 34 on HEAD (not the 32 an old memory claims); the changed files add zero.
