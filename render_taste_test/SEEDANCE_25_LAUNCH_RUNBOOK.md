# Seedance 2.5 Launch-Day Runbook

**Purpose:** ride the 2.5 launch hype wave with a great post within hours of public access — prepared assets + craft + speed, not improvisation. Model-launch hype is a proven reaction wave (archive evidence: `veo3`/`sora2` are top hashtags in the ≥1M-view class; the 29M Veo3 cat was launch-wave content).
**Trigger:** Seedance 2.5 reaches public availability (announced 2026-06-24 at FORCE; launch targeted July 2026). Watch: Volcano Engine / Dreamina announcements, Higgsfield model list.
**Standing rules that do NOT relax on launch day:** docs before credits; state cost before every paid render; reference-grounded only for known characters; your eye is the post gate — a bad render does not ship because the wave is hot. BUG-002's anatomy (rushed = no refs, no craft, cold judgment) is exactly what launch adrenaline reproduces. This runbook exists to prevent the rerun.

---

## What's known / unknown (as of 2026-07-02)

- **Claimed:** native 30s single-segment (no stitching), up to 50 multimodal references (2.0: ~12), native 4K 10-bit, region editing, unified audio-video generation.
- **Unknown:** pricing, Higgsfield availability/lag, real quality vs demo reel, generation latency, **IP-filter strictness** (MPA hit 2.0 with cease-and-desist over copyrighted characters — 2.5 may refuse recognizable fictional characters; that's our whole lane, so the runbook branches on it).

---

## T-minus prep (do THIS WEEK, all have lead times)

- [ ] **Pick 2–3 candidate characters** (slots below). Criteria: beloved + fandom currently active + strong visual signature (outfit/silhouette survives a render) + an obvious wish OR satire angle. Diversify regimes: ≥1 photoreal-fictional, ≥1 stylized anime/gacha.
  - ⬜ Candidate 1: Evie (Stellar Blade) — refs partially exist from the spike; wish angle = the epic showcase fans argue about
  - ⬜ Candidate 2: ______________ (stylized/anime — fill in from current fandom heat)
  - ⬜ Candidate 3: ______________ (optional)
- [ ] **Curate reference sets** — 3–5 canonical key-art images per candidate into `render_taste_test/launch_refs/<character>/`. Verify by eye: signature outfit, clean face angles. (2.5 takes up to 50 refs; 3–5 GOOD ones beat 50 random ones — spike lesson: ref quality is the identity lever.)
- [ ] **Platform access** — day-one probably means FIRST-PARTY, not Higgsfield: check/create Dreamina (CapCut) account; check Volcano Engine API signup friction from here; confirm payment works. Note where 2.0 currently runs for you as the fallback console.
- [ ] **Pre-authorize the launch-day budget** — decide NOW, calm: ⬜ ____ credits/$ hard cap for the day (suggest: enough for 1 cheap probe + 2 hero generations + 1 retry; on 2.0 economics ≈ 72cr/shot, assume 2.5 ≥ that).
- [ ] **Dialect pre-read** — lanshu masterclasses 15/17/19 (Seedance timeline prompting, @-reference tags, Omni Ref) + `video_model_system_guide.md` L108–322. 2.5's dialect will be closest to these; the delta arrives launch morning.
- [ ] **Posting readiness** — TikTok account logged in, AIGC label steps rehearsed (per-post, "More options" at post time), hook-card overlay workflow ready, music source (Sonilo) ready.
- [ ] **Stage B status check** — if the text path is live-verified by launch, the launch wave itself goes through `pitch_angles --topic "Seedance 2.5"` for story pitches. If not, hand-write the pitch using the story schema shape (mode, desired_moment, 3–6 beats, shot variety, hook line).

---

## Launch morning (T+0, in order — do not reorder)

1. **Read ByteDance's official 2.5 prompt guide FIRST.** Docs before credits, even today. Skim for: dialect changes vs 2.0, reference syntax, duration/resolution params, content-policy notes.
2. **One cheap IP probe** (state cost first): shortest/cheapest generation of Candidate 1 with references. Two questions: does it render the character at all (filter check)? Does identity hold?
3. **Branch:**
   - **IP renders fine →** fan-IP lane. Pick the pitch (Stage B on the launch wave, or the pre-written candidate pitch). Wish or satire per what the launch discourse is doing.
   - **IP blocked/refused →** fallback lane: impossible-spectacle showcase content (no recognizable character; the hype tag carries reach). The fan-IP lane stays on Kling/Veo as today.
4. **Generate the hero clip(s)** — inside the pre-authorized cap. 2.5's pitch: ONE native multi-shot 30s generation from beats + refs. If output disappoints vs the demo-reel hype → kill criterion below.
5. **Assemble + polish** — hook card only (caption restraint), music, AIGC label. If 2.5's unified audio delivers usable narration/SFX, skip TTS; otherwise narrate later — do not block the post on audio perfection.
6. **Post** with launch hashtags (the model name IS the wave tag: `#seedance25` + platform-native variants) while the hype is hours old, not days.
7. **Record** — `scripts/record_post.py`; log actual spend vs cap; note dialect learnings in this file.

**Kill criterion:** if the probe + one retry both look clearly worse than your current Kling/Veo stack, DO NOT force a 2.5 post — post the same idea on the proven stack with the launch-tag angle ("classic models vs the hype") or skip the day. A bad render riding a hot wave is still slop; the account promise is quality.

---

## T+1 and after

- Run the real bake-off (spec `2026-07-01-stage-b-story-craft-design.md` §10.6): consistency-drift fix? fan-IP renderability? quality-per-credit vs Kling/Veo/nano-banana? Winners take routing slots; `MODEL_ROUTING.md` gets updated with MEASURED verdicts, not launch claims.
- Feed findings into the writer/executor spec brainstorm (its opening item is exactly this check).
- Never single-vendor: whatever 2.5 wins, Veo/Kling stay routable — the MPA/IP-filter risk is permanent.
