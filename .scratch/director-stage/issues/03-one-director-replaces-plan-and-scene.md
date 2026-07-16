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

**Status:** ready-for-agent

- [ ] The writer makes exactly one LLM call per package; the fake LLM in tests no longer needs to answer two response models.
- [ ] `motion_intent` no longer exists in any schema or prompt.
- [ ] The director receives each beat's own `visual_line` — not a paraphrase — and emits `scene_line`.
- [ ] Every craft rule that lived in the SCENE prompt is present in the director prompt and still enforced.
- [ ] The director's action rule permits one continuous move spanning several sub-motions.
- [ ] The director prompt instructs expression as a folded-in change at close-ups, and does not add an expression field.
- [ ] The package shape reaching the adapter is unchanged — this ticket is invisible downstream.
- [ ] Existing writer tests (word budget, retry-once-with-feedback, beat-count mismatch, silent-beat) pass against the merged call, adapted only where they named the deleted stage.
- [ ] The model-agnostic split is gone; nothing pretends the plan layer is render-model-neutral.
- [ ] `uv run pytest`, `uv run ruff check .`, `uv run mypy src/` all pass.
