# Shot-Craft Cheat-Sheet (distilled from ai_video_resources/image-video-director/)

Purpose: director's reference for hand-making cut-based videos. Replaces the
morph-chain approach that rotted (see _frames/ — seg1 photoreal → seg3 grey-dot).

---

## THE BIG ONE: Kling 3.0 does multi-shot in ONE generation

Don't render N clips + ffmpeg stitch (that's the fallback). First try:
write ONE prompt with labeled shots, Kling cuts internally.

- `SHOT 1:`, `SHOT 2:`, `SHOT 3:` ... up to 6 shots / 15s.
- Model handles cuts, transitions, continuity automatically.
- Kling = "universe-strongest consistency" across shot changes (the Hole-2 fix).
- This is the OPPOSITE of morph: cuts are native, not fought.

---

## The shot formula (per shot, one each)

ONE camera move + ONE subject action + ONE beat. Never stack moves.

Order inside a shot: **CAMERA framing first → SUBJECT → ACTION → (audio).**
Models parse filmmaker vocab first; camera specs take priority.

Bad: "actor walks across room" (underspecified → drift, jump cuts).
Good: "actor takes four steps to the window, pauses, pulls curtain on final second."

---

## The 3-shot structure (vary the distance — trailer logic)

- SHOT 1 = ESTABLISH — wide, "where are we", show the whole impossible world.
- SHOT 2 = DETAIL — closer, one specific wonder inside it.
- SHOT 3 = REVEAL / HUMAN — payoff, or a person reacting so scale lands.

---

## CONSISTENCY across cuts (Hole-2 answer)

"Consistency beats poetry." Pick ONE identity sentence per subject, repeat it
VERBATIM at each shot. Don't vary phrasing ("the whale" → "it" → "the creature"
causes identity drift / role swaps).

Format: ANCHORS block up top (subject + key props described once), then shots
reuse those exact words.

WARNING: if shot endpoints disagree on identity/geography, the model MORPHS
instead of cutting. (This is literally what killed the pool.) Keep anchors stable.

---

## Camera words that work (validated)

low angle, high angle, overhead, establishing wide, tracking, dolly, crane,
orbit, handheld, macro, FPV, over-the-shoulder, POV, profile.
Lens: 35mm, 85mm, 100mm macro. Aperture: f/2.8 (shallow), f/11 (deep focus).

## Lighting (combine direction + quality + temperature in one phrase)

"soft side lighting during golden hour" = most efficient pattern.
back lit / side lit / silhouette / rim light / lens flare / practical lighting.
Name the source: "practical light from warm bar lamps."

## Color (film-stock anchors steer best)

"Kodak Portra 400", "cinematic teal and orange grade", "deep saturated cerulean".
Concrete palettes > vibe words.

## Atmosphere (make air a renderable object)

"heavy atmospheric haze", "dust particles in a single beam", "wet asphalt
reflecting neon". Authenticity cues (2026 trend): "natural grain", "slight
underexposure", "handheld micro-shake" — audiences favor authentic over polished.

---

## DEAD WORDS (wasted, never use)

"stunning", "breathtaking", "ultra-detailed", "best quality", "masterpiece",
"epic", "dramatic" (without a fixture), "cinematic" (alone, no props/light).
Every emotional word MUST pair with something the camera can see.

## TRAPS

- Conceptual not depictable: "hacking the mainframe" fails → "typing on keyboard" works.
- "rule of thirds" → can draw literal grid lines. Say "subject on right third."
- Too many shots for the runtime → smeary rushed transitions. Give each beat seconds.
- Image-to-video: do NOT describe the image. Prompt only camera + motion + timing.
