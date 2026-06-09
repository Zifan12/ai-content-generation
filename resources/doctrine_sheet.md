# Directing Doctrine Sheet

> Model-agnostic directing truths mined from `lanshu-awesome-ai-video-kit`
> (4 prompter skills + methodology docs 03 storyboard-timing / 04 emotion-externalization /
> 06 constraint-list). Model syntax stripped (`@图片N`, word counts, `镜头N` labels, channel
> markers). Kept only cinematography-level truths.
>
> **Provenance note:** the kit is external human doctrine (official OpenAI / Google / ByteDance /
> Kling guides). This sheet is the *human-taste anchor* for the v1 writer eval: it feeds the judge
> rubric anchors (`config/writer_rubric_v1.yaml`, Task 2) now, and the writer system-prompt upgrade
> (separate spec) later. If the taste here is wrong, every downstream score inherits the error.
>
> **Tags:** each entry feeds one judge dimension — `premise_fidelity` / `convergence` /
> `principle_execution` / `vividness` — or `writer-only` (seeds the later writer spec, not a judge
> dimension).
>
> **STATUS: DRAFT (AI-synthesized from the candidate pool). Awaiting user taste-review.**
> Debatable tags flagged inline with ⚠. `premise_fidelity` coverage is thin — the kit assumes you
> already have a premise, so it speaks mostly to craft; premise-adherence anchors may need taste
> sourced outside the kit.

---

## vividness — prose specificity, NOT scene energy (a calm beat can be a 5)

### V1. Externalize emotion into concrete body detail — never name it
The judge of "vivid" is whether the feeling is shown in the body and the camera, not stated.
- ❌ "she's very sad" / "he's furious"
- ✅ "head down, shoulders trembling, fingers clenching her sleeve, eyes red but tears unfallen" /
  "fists clenched, jaw tight, chest heaving, words forced through his teeth"

### V2. Specific verbs, not abstract ones
- ❌ "a man runs nervously," "they fight"
- ✅ "slowly breaks into a run with ragged breathing," "raises a hand slowly / plants a foot hard"

### V3. A named light source, not "dramatic lighting"
- ❌ "dramatic lighting," "cinematic light"
- ✅ "warm tungsten side-light," "low blue-gold light on the horizon," "neon rim light"

### V4. Tactile / physical detail anchors realism
- ✅ "steam billows through the lantern light," "neon reflections on wet pavement,"
  grain / sweat / fabric ripple / drifting hair

### V5. Ground the impossible in real physics ⚠ (could tag premise_fidelity instead)
Surreal / impossible subjects read as real only when anchored to physical interaction.
- ❌ a floating impossible object described abstractly
- ✅ "the stone crumbles," "the torches flicker," "dust kicks up where it lands"

---

## convergence — do the 3 shots build to something, or just sit beside each other

### C1. Shots form an arc: establish → turn → release
Order by event sequence; open with a setup/contrast beat so the turn lands.
- ❌ three disconnected pretty shots
- ✅ shot 1 warm/relaxed setup (contrast) → shot 2 the turn (fixed cam + close-up, emotion locked in
  the face) → shot 3 release (pull-back + curled posture; the feeling is *seen, not narrated*)

### C2. Shots link causally, not as a list
- ✅ "sits → hesitates → speaks → the other reacts → shared laugh" (cause/escalation between beats)

### C3. Every beat resolves — explicit motion endpoint, no hanging action ⚠ (could tag principle_execution)
An action with no terminal state stalls the beat and the arc.
- ❌ "her body engulfed by glowing particles" (no end)
- ✅ "…then settles into her new form" / "…then settles back / fades out"

---

## principle_execution — did it execute the principle it committed to, with discipline

### P1. One restraint per beat: a single camera move, 1–2 key actions ⚠ (P1 vs C/V is debatable)
Discipline reads as intent; clutter reads as noise. Too many actions dilute the focus.
- ❌ push + pull + pan in one shot; five micro-actions stacked
- ✅ one move (e.g. pull-back only); 1–2 load-bearing actions per beat

### P2. A coherent aesthetic — no contradictory descriptors that cancel
- ❌ "8mm film grain" + "4K ultra sharp"; "slow motion" + "high-speed action"; >2 artist styles
- ✅ one coherent look, committed to

---

## premise_fidelity — did it stay true to the premise / subject (kit coverage thin — fill from own taste)

### F1. Subject stays consistent across shots — stable identity, no drift or duplication
- ❌ ambiguous pronouns; the subject's look/clothing shifts shot-to-shot; accidental identical twins
- ✅ one stable identity referenced consistently ("the cop" / "the thief"), held across all 3 beats

---

## writer-only — seeds the later writer system-prompt spec, NOT a judge dimension

- **WO1. Subject-first, action-second.** ❌ "Walking through a forest, a woman…" → ✅ "A woman in
  hiking gear walking through a forest…" (prompt word-order; a judge reading prose won't grade it)
- **WO2. Don't over-specify per-beat timing.** Exact seconds ("0–3s") destabilize pacing; order by
  sequence and let rhythm emerge.
- **WO3. Image-to-video: describe only the change, never re-describe what the keyframe already shows.**
  ❌ "a red sports car with chrome wheels…" → ✅ "the headlights blaze on, the engine roars, the rear
  tires spin." (relevant to how `end_keyframe` is written, not to judging the package)
- **WO4. Audio as an emotional/causal layer** — kit's native-audio feature; the writer outputs
  keyframes (no audio), so out of scope for this eval.
- **WO5. Negative-constraint hygiene** (no watermark/logo/subtitles, face stability, no extra limbs,
  no sliding feet) — conformance, already enforced by the writer prompt; this is the v0 regex's job,
  NOT a judgment dimension.
