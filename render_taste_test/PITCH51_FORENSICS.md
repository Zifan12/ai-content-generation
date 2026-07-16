# Pitch-51 render forensics — 2026-07-16, 67.5cr, single_gen, Seedance 2.0

**Read this before proposing any render fix.** It is the most heavily-evidenced render
post-mortem on file: one paid render (67.5cr, 15s/720p/9:16, 5 refs) measured frame-by-frame,
plus four parallel corpus sweeps (`video-researcher`, all full-Reads, all cited to file:line).
Artifacts: `output/smoke_runs/render_20260716_002107_2899ec1/` (take_1.mp4 = raw 24fps,
final.mp4 = assembled, frames/, strip/, lift/).

**Headline: the render was the FIRST with clean refs (2/character, no turnaround sheet) — and
the payoff action still rendered in ZERO frames. The lane was not the cause.**

---

## 1. What was measured (not inferred)

| Claim | Method | Result |
|---|---|---|
| It is NOT a slideshow | frame-delta on raw take, 360 frames | **0 near-zero frames (0.0%)**, mean motion 7.65, peak 53.8, sustained 2s–14s |
| The LIFT never renders | 12fps tile across 8.2–10.0s | **8.2–9.17s: on the floor. 9.25s (next frame): already cradled on the bed.** Zero frames of the lift |
| Assembly manufactured judder | `mpdecimate` on both files | raw take 24fps/361 unique, **assembled 30fps/451 → drops back to 361 = 90 duplicated frames**. FIXED (`_FPS = 24`, commit 9f50175) |
| Model allocates time badly | cut detection + per-second motion | cuts at 2.97/3.90/5.23/9.20s for 4 authored shots. **~0.9s** on the wrist grab, **5.7s (38%)** parked on one near-static two-shot |
| Location ref = camera | compared `room.jpg` to 4–7s | model **reproduced the reference photo's exact camera** and composited characters in. Our "Wide shot, from the open doorway" was ignored |
| Identity held | frames vs refs | Elfaria and Will both match refs (blue hair/freckles/diamond trim; teal hair/glasses/ahoge). **The 2-ref fix worked** |
| Register inverted | payoff frames | she **looks into the lens** with a wide open smile. Asked for "a cool, satisfied smirk" |
| Two doors | user observation, confirmed against text | room has ONE door; text carried two ("heavy wooden door on the far wall" + "just inside the open doorway"). Model rendered both |

---

## 2. The four corpus sweeps — what they actually settled

### 2a. The lift failed because the line was BEAT-FREE, not because of the lane

Shipped text: *"Elfaria lifts him from the floor onto the bed, cradling him against her chest."*

That is structurally the corpus's canonical BAD example.
- **[cited]** `image-video-director/03-video-prompting-techniques.md:15` — *"'Actor walks across the room' is underspecified. The model guesses pace, path, camera relationship. That causes drift, weird gait, jump cuts."* A bare displacement verb naming start+end with nothing between.
- **[cited]** `image-video-director/03:14,16` — the fix is BEATS: *"Express action as beats (counts, pauses, 'final second')"*; worked example *"Actor takes four steps to the window, pauses, and pulls the curtain in the final second."*
- **[cited]** `lanshu .../03-分镜时序.md:3,14,16` — the model *"decouples space and time"* (空间和时间解耦); an undifferentiated sentence means *"模型无法判断节奏、镜头切换、动作起止"* (cannot judge pacing, cuts, or an action's **start and end**).

Corpus-compliant rewrite would be: *"grips his wrist, pulls him upright, lifts him onto the mattress in one motion, then draws him against her chest"* — countable sub-motions.

**WE ALREADY HAVE THIS RULE AND IT WAS IGNORED.** `config/render_rules.yaml` `motion_craft.action_as_beats` states it verbatim and is injected into the director prompt. The director received it, plus `one_move_one_action`, plus DIRECTOR_SYSTEM_PROMPT's "countable physical beats" — three statements — and still emitted a beat-free line.

### 2b. D4 fixed the wrong half (this session's own error)

Pitch 47's bug was the WRITER collapsing "lifts…and cradles" → "cradles". Tickets 02/03 restored
**verb count**. The corpus's fix was **beat decomposition**. On pitch 51 both verbs were present
and the lift still rendered zero frames. Verb count was never the mechanism.

**D4's principle is NOT contradicted** (an earlier read of this session claimed doc 19 conflicts —
it does not): **[cited]** `Dan Kieft:471` binds two verbs into one arc ("he speaks and immediately
whips his head around"); `03:16` calls three sub-motions ONE action. `19-seedance-masterclass-round3.md:318-324`
forbids *compound UNRELATED* actions ("running and reloading while shouting"). Flowing chain ≠
compound. They agree. **D4 is right and insufficient.**

### 2c. "Motion cannot carry across a cut" — OUR OWN NOTE OVERREACHES ITS SOURCES

The PRD's rejected-design note ("the corpus says end on a cut… State may carry; motion may not")
traces to **[cited]** `08-避坑12问.md:63-75` (extend-splice jump-cut) and `18-kling-masterclass.md:189-194`
— **both about stitching SEPARATELY-GENERATED clips**, not internal cuts inside one generation.
**[cited]** `03:25-33` says Seedance's native multi-shot produces *"introduction, development, and
climax in one generation cycle"* with *"automatic camera angle adjustments, shot transitions, and
continuity"*. `config/render_rules.yaml:345` (`end_start_chain`) applies the splice-boundary rule to
our internal shots — a project extrapolation beyond its cited source. **The corpus does NOT support
"motion never carries across ANY cut."**

### 2d. Shot count and character count were NEVER the problem

- **[cited]** `Dan Kieft:47-51` and `video_model_system_guide.md:499-503`: 11–15s → **4–6 shots**. We ran 4. Mid-bracket.
- **[cited]** `15-seedance-masterclass.md:136-139`: max 2–3 main characters/shot. We ran 2.
- Corpus does NOT converge on one Seedance ceiling: 6 (`Dan Kieft:51`), 6 (guide), 10 (`15:83`), and a "6/15s" that actually belongs to **Kling** (`03:27`).

### 2e. Per-shot screen time has NO lever on our platform

- **[cited]** the documented lever is bracket timestamps (`15:81-88`, `19:349-355`, `guide:455-476`) — **measured-REJECTED on Higgsfield CLI** (`seedance_motion_test/FINDINGS.md:21`, `render_rules.yaml:136`).
- **[cited]** `03-分镜时序.md:9-10` independently warns *don't* force per-segment duration — *"模型对精确时间的支持不稳定"*.
- **[cited]** `19:195-196` claims *"no timestamps needed, the AI evenly distributes the total duration"* — **our render falsifies this for Higgsfield** (0.9s vs 5.7s vs a dropped shot). That claim is CapCut-scoped.
- **word-count → screen-time correlation is absent from the entire corpus** (confirmed by full-read, not grep).
- **The zero-frame shot is UNDOCUMENTED anywhere.** New data point; do not claim a cause.

### 2f. Refs BEAT prompts — and our identity refs are wrong

- **[cited]** `reference-material-playbook.md:112-114` — *"prompt contradicting refs → blend or per-shot alternation. Prompt must describe the ref or stay silent on ref-covered attributes."*
- **[cited]** `01-model-registry.md:212` — Seedance 2.0 is *"Strong at single-scene reference adherence."* Worst model to fight in text.
- **[cited]** `05-misconceptions.md:29-31` / `03:110-116` — *"the image IS the visual prompt."*
- **[cited] `reference-material-playbook.md:59-60` — "neutral expression mandatory (smiling ref reshapes face into a 'midpoint face')". OUR `sheet_identity.png` FOR ELFARIA IS SMILING, EYES ON LENS.** Verified by eye.
- **[cited]** `reference-material-playbook.md:86-87` — *"Pose belongs to the SHOT… identity belongs to the refs."*
- **[cited]** `Dan Kieft:507-520` — the recipe our sheets were built from explicitly prescribes *"eyes looking straight into the camera lens"* for the identity plate. **The corpus CONTRADICTS ITSELF on eyeline** and nobody warns that a still ref's gaze carries into video. Expression → neutral is safe and cited. Eyeline → unresolved, needs an A/B.

**Natural experiment inside this one render:** Will's ref is neutral/deadpan → Will renders correctly
vacant. Elfaria's ref smiles at the lens → Elfaria smiles at the lens on the payoff. Same render,
same model, same prompt discipline. Only the ref's expression differs.

### 2g. Undocumented gaps the corpus cannot answer (stop looking)

- Whether Higgsfield's **positional** ref-binding has any role-declaration equivalent to Seedance-native `@Image1 as first frame` vs `environment only`. `INDEX.md:22`: *"Higgsfield binds refs positionally, NOT @-tags; cherry-pick claims, never adopt wholesale."* **The single biggest gap behind the camera-lock bug.**
- **[cited]** `video_model_system_guide.md:347-351` — *"Every uploaded file MUST have an explicit role stated in the prompt. Uploading files without @ tags causes ambiguous processing."* We upload 5 images and role-declare NONE. Our adapter says "The setting is shown in image5" — that is identity binding, not a role.
- Input-ref aspect ratio (16:9) vs output (9:16): **silent**, despite heavy output-AR coverage.
- What shot-scale a LOCATION ref should be: **silent** except `17-happyhorse-masterclass.md:139` — *"环境参考图里不要放主角"* (don't put the character in it).
- Object/architecture duplication (our two doors): **zero coverage**. The "twins" pitfall (`08:79-101`) is people-only, caused by multi-view refs.
- Camera-look as a named artifact: **silent**. Not among the 12 pitfalls.
- Attention dilution is real though — **[cited]** `reference-material-playbook.md:109-111`: *"too many / busy refs → identity signal competes with background… unless refs are clean and role-tagged."* Our room ref competes with the faces.

---

## 3. THE PROCESS FAILURE — the most important finding

**Three of the four failures were already written down in our own files before this render:**

1. `DECISIONS_LOCKED.md:118-121` (billing-verified **2026-07-13**): *"a 15s/5-shot single generation produced transition garbage at ~6-9s… while 7-8s per-scene clips + hard-cut splice cleared it."*
2. `render_rules.yaml` `motion_craft.action_as_beats` — the beats rule, already injected into the director.
3. `reference-material-playbook.md:59-60` — neutral expression mandatory, while our generator ships a smiling ref.

**And worse:** `docs/superpowers/plans/2026-07-12-anime-tutorial-lane.md:59-71` (VERDICT, 2026-07-13)
records that the single-gen vs per-scene-splice A/B **already ran on pitch 47** — single-gen gave
6-9s transition garbage; splice was *"better but"* still *"motion-sparse (no actual animation)"* —
and that **no further renders were authorized after that verdict.** The 2026-07-16 render went ahead
on the already-deprecated architecture. Nobody checked.

**The disease is not the lane, the shot count, or the beat structure. It is that render questions get
answered by reasoning instead of by the corpus, and then credits are spent rediscovering what was
already on file.** The knowledge exists; the enforcement does not. Rules live in prompts, and prompts
are suggestions a model resolves toward least resistance.

---

## 4. What is NOT settled — do not let a future session pretend otherwise

- **Splice is not a proven fix.** The A/B ran; splice was "better but" still failed the motion bar. It also re-runs identity per clip (drift risk) and costs ~2x (126cr for 4 shots vs 67.5).
- **Nothing has isolated why the lift got zero frames.** Beat-free prose is the best-evidenced hypothesis and is UNTESTED. The cheap next test is a beats rewrite of the SAME shot, same lane — not a lane change.
- **Eyeline (at-lens vs off-axis) is a live corpus contradiction.** Needs a controlled 2-render A/B, same text, one camera-facing ref vs one off-axis.
- **The motion bar itself has never been cleared** by any lane, on any pitch, to date.

## 5. Errors made while analysing this render (recorded so they are not repeated)

1. "The bed and the lift survive" — true of the PROMPT, false of the SCREEN. Claimed off the composed text + 3 frames.
2. "4 shots is too many" — it is mid-bracket. Invented, not cited.
3. "An action spanning a cut is structurally unrenderable" — stated as fact; the sources are about cross-generation splices (§2c).
4. "Splice is the fork" — the A/B had already run and already failed (§3).
5. First frame-delta pass reported "frozen every 1.0s" — that was the 24→30fps duplication artifact, nearly filed as a model defect. The perfect 1.0s spacing gave it away: **real freezing does not keep time.**
