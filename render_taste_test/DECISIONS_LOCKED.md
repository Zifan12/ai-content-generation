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
  (06-27 spec §5).

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

---

*Change policy: Tier 1 changes require a paid-render counter-evidence note (date +
artifact path). Tier 2 changes require a spec supersession. Either way, edit THIS
file in the same commit — it is the file other docs point at.*
