# DECISIONS_LOCKED.md — render-craft source of truth

> **Status note (2026-07-04):** this file was referenced by name in `AGENTS.md`,
> `render_taste_test/MODEL_ROUTING.md` (L23), and the audit issue
> `.scratch/codebase-audit-2026-07-01/issues/10-render-routing-disconnected.md`,
> but never existed on disk (confirmed in `render_taste_test/evie_grounded/PLAN.md` §2,
> "dangling pointer"). Written now, consolidating the locked decisions from
> `MODEL_ROUTING.md`, `SHOT_CRAFT_CHEATSHEET.md`, BUG-002 + the 2026-07-01 grounded
> A/B (`evie_grounded/PLAN.md` §8), `config/render_rules.yaml` evidence notes, and the
> 2026-07-04 multi-shot writer/render redesign spec
> (`docs/superpowers/specs/2026-07-04-multishot-writer-render-redesign.md`).
>
> Two tiers below. **Tier 1 = evidence-locked** (paid renders / measured behavior —
> do not re-derive, do not contradict; overturn only with a new paid render that
> says otherwise). **Tier 2 = design-locked** (decided in a ratified spec; carries a
> named validation gate where one is pending).

---

## Tier 1 — LOCKED BY RENDER EVIDENCE

### L1. Route by SHOT CONTENT, never a default model
- Fluid / water / physics / lighting realism → **Veo 3.1** (`veo3_1`).
  Evidence 2026-06-17: same pool still + same drain prompt — Kling rendered a cheap
  CGI vortex, Veo rendered a physically-real concave funnel with surface tension.
- Impossible physics that must HOLD an end-state → **Minimax Hailuo** (`minimax_hailuo`).
  Evidence 2026-06-21: Hailuo held the "edges stay full" pool drain to the final
  frame where Veo failed 3×. Hailuo requires a seed image on the Higgsfield CLI
  (still-first pipeline satisfies this).
- Cross-shot consistency / cheap / multishot → **Kling 3.0** (`kling3_0`)
  (7.5cr/5s, 15cr/10s MEASURED).
- Narrative arc / epic spectacle / directorial ~20s → **Seedance 2.0** (`seedance_2_0`) (~72cr).
- Still anchor → **nano-banana Pro** (`nano_banana_2`) (June-14 taste test 4/4 photoreal;
  CLI-name trap: `nano_banana_2` *displays* as "Nano Banana Pro" — trust the CLI name).
- Veo cannot pin an impossible END state from words alone (3 failed renders,
  2026-06-18) → keyframe escalation (`--start-image`/`--end-image`) or re-route to Hailuo.

### L2. Connect shots by CRAFT, never last-frame handoff (2026-06-18 fork-resolved)
> **SCOPE NOTE (2026-07-06/07, motion-native spec):** in the v1 scene lane there is
> only ONE generation — no shot-to-shot connection problem exists, so the craft
> rules below scope-narrow to nothing in v1. The handoff BAN itself stands and
> re-applies the moment any multi-generation path (extend-continuation, breakouts)
> returns.
- Feeding clip N's last frame into clip N+1 = photocopy-of-a-photocopy → grey mush.
  BANNED. (This killed the original morph-chain: `render_taste_test/_frames/`
  seg1 photoreal → seg3 grey-dot.)
- Instead: **fresh clean still per shot** generated from the ORIGINAL reference
  (never a degraded frame), **match-cut** on action/shape between shots, **shared
  style/world anchor repeated verbatim per shot**, **post-assembly** concatenation
  (plain video editing, not model chaining).
- Cap each clip **6–8 s** (`video_model_system_guide.md` L420).
- Clarification (INDEX.md conflict audit 2026-06-19): the banned thing is
  last-frame HANDOFF chaining. Deliberate A→B morph is a separate, unused tool;
  Kling's native multi-shot-in-one-generation is internal CUTS, not handoff —
  it does not violate this lock.

### L3. Reference-grounding is MANDATORY (BUG-002 → 2026-07-01 A/B)
- Text-only character stills produce wrong outfit + wrong face (BUG-002: black
  poncho instead of Eve's pure-white suit; "AI slop at a glance").
- Feeding real canonical key-art into the still model flipped wrong→right with
  grounding as the single changed variable (`evie_grounded/` spike, ~28.5cr).
  **Every character still is grounded on real key-art. No exceptions.**
- Same mechanism carries SOURCE ART STYLE, not just identity — the reference
  anchors both (the redesign's source-style register rides on this).
- Fictional-character art is the sanctioned reference path (doc 20 L440:
  human-reference use suspended Feb 2026; real-actor likeness stays deferred).

### L4. Grounding alone does NOT solve cross-shot consistency (2026-07-01)
- Independently generated stills drift in face + fine costume detail shot-to-shot
  (nano-banana has no seed; each generation re-interprets the reference).
- More/better references CANNOT fix this — it needs a lock mechanism.
  Candidates identified: Higgsfield Soul ID / Kling multi-shot-in-one-generation /
  seed-capable still model. Resolution: Tier 2 D-6 below.

### L5. Shot-craft rules (BUG-002 #3 + evie C1/C2 PASS)
- Vary distance AND angle across shots (establish wide → detail medium → reveal
  close). Three near-identical frontal/medium shots = the BUG-002 failure.
- ONE camera move + ONE subject action per shot; action as countable beats.
- One identity sentence per subject in an ANCHORS block, repeated VERBATIM every
  shot — varied phrasing causes identity drift / role swaps.
- No dead words ("stunning/epic/cinematic-alone/masterpiece/8K"); every emotional
  word pairs with something the camera can see.

### L6. Caption restraint (BUG-002 #4)
- ONE hook card only. No explainer captions on later shots.

### L7. Cost discipline (ADR-0007 / project render rule)
- State credit cost BEFORE any paid render, always. No silent spends.
- Kling-cheap-first; escalate to Seedance (~72cr) only when the look demands it
  (06-27 spec §5). [Scene lane: Seedance IS the lane — the rule's routing half is
  legacy; the state-cost-first half is eternal.]
- **MEASURED rates (billing ledger `higgsfield account transactions`, 2026-07-06/07
  — billing beats session notes AND the cost subcommand):**
  - Seedance 2.0: **linear 4.5cr/s @720p** (22.5/45/67.5 for 5/10/15s, kept
    charges); ~9cr/s @1080p inferred from refunded attempts (90/10s, 135/15s).
  - GPT Image 2: **7cr/image** (6 sheet generations, 2026-07-07).
  - nano_banana_2: 2cr/image. TTS text2speech_v2: 0.15cr/line.
  - Failed/rejected jobs are REFUNDED (confirmed across bisect + validation runs).

### L8. Motion-native scene lane — MEASURED CLI facts (2026-07-06 bisect + 07-07 validation)
- **Duration ≤15s works via CLI** (15.07s outputs verified twice). The bisect's own
  "15s fails always" verdict was DISPROVEN same-day by a clean probe — early
  failures were confounded/transient. 10s = D1 v1 target, not a cap.
- **Bracketed timestamps (`[0-3s]`) rejected** at any duration >5s; prose-chained
  shots ("Then cut to: ...") cut internally — the load-bearing grammar.
- **Reference binding is TEXTUAL-POSITIONAL** — prose must name "(imageN)" per
  character; upload order defines N. Path convention refs/<slug>/ feeds it.
- **≤9 image refs / ≤12 files total / ≤3000-char prompt** enforced as adapter
  crash-loud guards; all three refused bad input live with 0cr wasted (2026-07-07).
- **Pipeline validation verdict (user, 2026-07-07): the UNATTENDED lane's pitch-24
  render is "better than the slideshow" — architecture VALIDATED.** Content quality
  (story sizing, narration voice, hook copy) failed on layers outside the render
  lane; workstreams tracked in PLAN.md 07-07 update + seedance_motion_test/FINDINGS.md.
- **Anime-tutorial-lane measured facts (2026-07-13, billing-verified, branch
  feat/anime-tutorial-lane):** soul-id UUIDs are REJECTED as seedance_2_0
  `--image-references` (job fails uncharged; same job minus souls succeeded —
  `render_taste_test/anime_tutorial_lane/take_1.mp4`); soul training = 25cr flat,
  requires a detectable face in EVERY image (back view → `face_not_found`,
  refunded); a 15s/5-shot single generation produced transition garbage at ~6-9s
  (matches guide L420 degradation warning) while 7-8s per-scene clips + hard-cut
  splice cleared it (user: "better but" — still below motion bar). Per-scene-clip
  architecture is COUNTER-EVIDENCE against D3's single-lane at ≥5-shot density,
  NOT yet a supersession — pending fresh-pitch validation. Harvested prompt rules:
  `config/render_rules.yaml` `sequence_craft_candidates` block. Verdict detail:
  plans/2026-07-12-anime-tutorial-lane.md.

---

## Tier 2 — LOCKED BY DESIGN (2026-07-04 redesign spec; gates named where pending)

> Full rationale + rejected alternatives: decision log D1–D15 in
> `docs/superpowers/specs/2026-07-04-multishot-writer-render-redesign.md`.

### D-register. Register = SOURCE-STYLE-MATCHED (found-footage retired)
The quality bar is "could be mistaken for footage from the source show" — anime
sources render as that show's animation register, live-action-styled sources as
that show's cinematography. The writer's old "found-footage / is-this-real?!"
photoreal register belonged to the retired single-8s-shot product and directly
contradicts the standing 06-27 spec ("source-faithful aesthetic", §9.4). Style is
carried by (a) the key-art reference into the still model and (b) a per-package
`style_anchor` line appended to every still prompt.

### D-consistency. Cross-shot lock = Kling multi-shot-in-one-generation (primary)
> **SUPERSEDED 2026-07-06 (motion-native spec D3) — Kling demoted to nothing in
> v1.** The scene lane renders the whole package as ONE Seedance generation;
> cross-shot consistency is solved by construction (single continuous model
> context, validated by the 07-07 pitch-24 render). The spike evidence below
> stays as Tier-1 history; the launch-mechanism decision it carried is dead.
**Spike ran 2026-07-04 (`kling_multishot_spike/PLAN.md`, 50cr total, user-judged):
PARTIAL-ACCEPT.** Split verdict:
- **Now Tier-1 evidence (spike-proven mechanics):**
  - Higgsfield's `kling3_0` DOES cut internally — but ONLY in Kling-native grammar:
    `Shot N (Xs-Ys): [angle] + [action] + [environment]. Audio: [...]` with explicit
    "Change angle to / Switch to" verbs. Seedance-style `SHOT N [Xs-Ys]:` labels
    render ONE continuous camera move instead (attempt-1 failure). The grammar is
    LOAD-BEARING — call-2 dialect conversion must emit it exactly.
  - Limits (doc 18 §5, spike-consistent): ≤500 chars/shot, ≥3s/shot, ≤6 shots/15s
    (4–5 recommended), 10s holds consistency better than 15s, multi-shot mutually
    exclusive with start+end-frame, ≤4 reference images.
- **Quality verdict (user, binding): identity across internal cuts only SLIGHTLY
  better than three independent grounded stills.** Face holds; fine costume detail
  (collar bulk, shoulder plates, hair length/shade) still drifts. ACCEPTED as the
  launch mechanism — cheapest option and directionally best — but NOT a solved
  problem; expect drift flags at the post gate.
- Beats routed elsewhere by content (fluid→Veo etc.) break out as separate
  fresh-grounded-still + i2v renders, same references + verbatim anchors.
- Soul ID = deferred escalation for a character that RECURS across many posts
  (training cost only amortizes then). Seed-capable still model sweep = fallback,
  NOT opened now (marginal-gain verdict didn't justify the spend yet).
- **New candidate (2026-07-05, informational — does NOT change the launch mechanism):
  Seedance 2.5** (announced 2026-06-23, public launch ~2026-07-03): native 30s
  single generation with up to 50 pooled multimodal refs. Our spec target (3–6
  clips, 12–25s) fits inside ONE generation — zero cross-shot problem by
  construction IF the pooled-conditioning claim holds (unverified, vendor claim).
  Spike when Higgsfield-available; apply the Kling-multishot skepticism (internal
  consistency was "only slightly better" there). Cost unknown — 2.0 is ~72cr,
  30s/4K likely well above; L7 preflight mandatory. See
  `ai_video_resources/reference-material-playbook.md` §1.
- **GATE (pending): ≤25cr validation spike** — does a grounded first frame hold
  identity across Kling's internal cuts? Not yet render-proven. Until the spike
  passes, this is design-locked, not evidence-locked.

### D-audio. Audio stack (per 06-27 spec §4: narration + captions + music/SFX)
- `narration_line` per beat → TTS narration via **Higgsfield `text2speech_v2`,
  variant `elevenlabs`** (D7 amended 2026-07-05: no OpenAI key on file; native
  job type bills the existing credit plan at a measured **0.15cr/line**). Mixed
  at assembly. No on-screen lip-synced dialogue at launch. Narrator voice =
  Sterling preset PLACEHOLDER — user auditions `higgsfield voices list` before
  the first posted video.
- Per-shot diegetic SFX = the video model's native audio (every motion prompt
  carries a concrete `Audio:` line; never "ambient sounds").
- Music: allowed under source-style register (the found-footage no-music rule is
  retired with that register). BGM via Sonilo when the package carries a
  `music_brief`; flat mix (BGM ~0.2 volume, 3s fade-out), no ducking in v1.

### D-text. "No on-screen text" constraint is scoped to the RENDERED FRAME
> **SUPERSEDED 2026-07-07 (native-quality-v2 spec) — no on-screen text AT ALL.**
> The hook card is deleted, not deferred to assembly: the video is pure picture +
> native sound, `hook_text` is forced None at the writer level, and the drawtext
> branch goes dormant. The evie-spike drawtext proof below stays as history only.
- `global_constraints.always_append` keeps suppressing baked-in text/subtitles/
  watermarks inside the render. The hook card is burned at ASSEMBLY (ffmpeg
  drawtext, proven in the evie spike) — no conflict with `hook_text`.

### D-routing-wire. The yaml routing table + constraint buckets are LIVE code
- Writer emits a per-shot `motion_tag` (values = `config/render_rules.yaml`
  routing keys, verbatim); a deterministic code router stamps
  `model_cli_id = rules.route(tag)[0]`. Routing is never an LLM decision.
- `rules.global_constraints(kind, style)` is appended to every prompt at adapter
  composition time. (Closes audit issue 10 — dead code in the render path.)

### D-compose. Prompt composition is CODE, not LLM discipline
- ANCHORS block, `style_anchor`, and global constraints are appended to prompts
  deterministically by the adapter. The LLM is never trusted to repeat an anchor
  verbatim.

### D-language. Seedance prompt body = CHINESE via translate-at-adapter (2026-07-13)
- **User decision 2026-07-13 (chat, no spec doc; user explicitly waived the 480p
  A/B — "trust that Chinese wins").** Basis: Dan Kieft doc L43 hard rule
  (OpenArt-verified), lanshu Chinese-first corpus for ByteDance models.
  **Higgsfield-CLI transfer UNVERIFIED — the named validation gate is the FIRST
  live Chinese render** (failed jobs refunded per L7, so the gate risks 0cr on
  rejection, full price only on a kept-but-bad render).
- Design: pipeline stays English end-to-end (writer, craft gate, grounding,
  dialogue floor unchanged); ONE translation step at render-job build time.
  Dialogue lines stay English inside quotes; refs stay positional "(imageN)"
  Latin. English mirror stored alongside the Chinese prompt for review/debug.
- Config: per-model dialect leaf (`prompt_language`) in `render_rules.yaml` —
  yaml-leaf pattern, so kling3_0/2.5 can flip later without code.
- Fallback: translation failure OR repeated Chinese-prompt job rejection → send
  the English prompt unchanged (loud log, not silent).
- Interaction note: sensitive-word filter behavior on Chinese text is unmeasured;
  if a Chinese prompt gets filter-killed, retest the same prompt in English
  before blaming content.

---

## L9. Pitch-51 paid render (2026-07-16, 67.5cr) — FIRST clean-ref render. Read the forensics.

**Full evidence + all citations: `render_taste_test/PITCH51_FORENSICS.md`.** Do not re-derive; do not
propose a render fix without reading it. Operational must-knows:

- **Refs are now headshot + full-body ONLY** (2/character, turnaround + detail sheets archived
  2026-07-15). Identity HELD on this render — both characters matched refs. The multi-view defect is
  fixed; renders from here are no longer confounded by it.
- **A beat-free action line does not render.** "lifts him from the floor onto the bed" is the corpus's
  canonical BAD shape (`image-video-director/03:15`) — it rendered in ZERO frames despite having 5.7s.
  The fix is countable beats (`03:14,16`), NOT verb count. Our own `render_rules.yaml`
  `motion_craft.action_as_beats` already says this and the director ignored it.
- **Our identity refs violate a cited baseline rule.** `reference-material-playbook.md:59-60`:
  "neutral expression mandatory (smiling ref reshapes face into a 'midpoint face')". Elfaria's
  `sheet_identity.png` smiles into the lens — and she renders smiling into the lens on the payoff,
  overriding every prompt rule we wrote. Will's ref is neutral and Will renders correctly. **Refs beat
  prompts** (`reference-material-playbook.md:112-114`); Seedance is "strong at single-scene reference
  adherence" (`01-model-registry.md:212`). See BUG-030.
- **The location ref DICTATES THE CAMERA.** For ~3s the render reproduced `room.jpg`'s exact camera
  and composited the characters in; our authored framing was ignored. We role-declare NONE of our 5
  uploads, and `video_model_system_guide.md:347-351` says un-role-tagged uploads cause "ambiguous
  processing" — but that is @-tag dialect and `INDEX.md:22` warns Higgsfield binds POSITIONALLY.
  **Unresolved; biggest open gap.**
- **Assembly was manufacturing judder.** It force-converted 24fps renders to 30fps, duplicating 90
  frames. Fixed (`_FPS = 24`, commit 9f50175). **Never resample; keep _FPS equal to what the model
  emits.** Every render judged before 2026-07-16 carried this.
- **NOT a slideshow — measured.** 360 frames, ZERO near-zero deltas, mean motion 7.65, sustained
  2s–14s. Use `tblend=difference,signalstats` on the RAW take (not the assembled file) to measure this
  again; it is free and beats eyeballing.
- **Shot count was never the problem.** 4 shots in 15s is mid-bracket (`Dan Kieft:47-51`,
  `guide:499-503`). 2 characters is within `15-seedance-masterclass.md:136-139`.
- **The model allocates screen time badly and there is NO lever.** It gave one beat ~0.9s and parked
  5.7s (38%) on a near-static two-shot. Bracket timestamps are measured-rejected here; word-count →
  screen-time is absent from the whole corpus.

**PROCESS (the real finding):** three of these four failures were already documented in our own files
before the render, and `docs/superpowers/plans/2026-07-12-anime-tutorial-lane.md:59-71` records that
the single-gen vs splice A/B ALREADY RAN on 2026-07-13 (splice = "better but", still motion-sparse)
**and that no further renders were authorized.** This render went ahead on the deprecated lane anyway.
Read the file before you spend.

---

## L10. POV camera-as-eyes register — PROVEN (2026-07-17, 60cr billing-verified, user-watch PASS)

**Full record: `render_taste_test/pov_probe/PROBE_SHEET.md` (local, untracked per this dir's
media policy). Two 10s/480p/9:16 text-only Seedance 2.0 single generations:**

- **POV register HOLDS** a full 10s continuous take — no angle switch, no third-person flip,
  no face/body leak. Load-bearing prompt lines: "the camera IS the [subject]'s eyes" +
  "an unseen [subject]" + **"No cuts, no zooms, natural head movement only"**
  (corpus-mandated: `methodology/15:163-169,380`).
- **BUG-031's motion class ANIMATES in POV register:** reach → grip → vertical lift toward
  the viewer's eyes drew beat-by-beat (probe 2, user-confirmed continuous, all beats). Does
  NOT retroactively fix BUG-031's third-person case.
- **Text-only worlds pass the quality bar** — zero reference images, prose-invented cave +
  prop, user verdict "Yes, build it."
- Motion measured (tblend): probe 1 mean 6.57, probe 2 mean 3.22, ZERO near-zero frames both.
- 480p rate reconfirmed: 3.0cr/s (30cr per 10s clip, billing 1554→1494 for both).
- Consumer: the POV pipeline (`.scratch/pov-pipeline/PRD.md`); grammar lands evidence-tagged
  in `config/render_rules.yaml` `pov_grammar`.

## L11. Canon-IP refs bind to the POV protagonist's limbs — PROVEN (2026-07-19, 30cr net, user-watch PASS)

**Full record: `render_taste_test/ip_probe/PROBE_SHEET.md` (local, untracked per this dir's media
policy). One 10s/480p/9:16 Seedance 2.0 generation, 4 reference crops (`refs/ultraman/`).**

- **Costume CROPS (limbs-only, no face/full-body) bind to the POV camera-holder's arms** — arms
  matched the official-art refs on the first roll. Zero corpus precedent existed; now measured.
- **The character is NOT summoned into frame as a separate figure** by feeding refs of an
  "unseen" protagonist. Load-bearing binding sentence, frozen verbatim (position: directly after
  the Subject sentence): *"The [PROTAGONIST]'s arms and hands are those of the character shown in
  image1, ..., imageN."*
- **Beam/energy-attack VFX renders in POV register** — kinetic dashed-particle-stream vocabulary,
  origin noun in the release clause. First watched beam evidence in repo or corpus.
- **Content filter PASSED with refs + action-wrapped combat phrasing** attached.
- **style_register's "No 3D, no cartoon, no VFX aesthetic" negation does NOT block beam VFX**
  (drew with the clause present) — RESEARCH-slice2 risk #10 closed, clause stays verbatim.
- Craft-tier findings (not register): payoff-reaction needs countable beats; sustained effects
  need an authored END beat (candidate rule, first instance); impact moments need their own
  audio event (existing rule, was under-authored by hand).
- Attempt 1a failed server-side with no reason and REFUNDED; identical retry succeeded —
  transient class (L8), diagnose-by-retry-once remains the correct first move.
- Consumer: POV slice ② ticket 11 (`.scratch/pov-pipeline/issues/11-ref-binding-compiler-craft.md`)
  freezes the binding clause into `pov_grammar`; asset-gate recipe (2-4 official-art crops of
  what-the-camera-sees) validated end to end.

*Change policy: Tier 1 changes require a paid-render counter-evidence note (date +
artifact path). Tier 2 changes require a spec supersession. Either way, edit THIS
file in the same commit — it is the file other docs point at.*
