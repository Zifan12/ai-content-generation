# Model Routing Cheat-Sheet — problem → model (Higgsfield CLI)

> WHY THIS FILE EXISTS: we kept defaulting to Kling and forgetting the registry.
> The knowledge was in `ai_video_resources/image-video-director/01-model-registry.md` but
> buried + never loaded. This is the SHORT always-check version. Read BEFORE any
> render. Pointer added to CLAUDE.md Architecture bullets so it loads each session.
>
> Source of truth (full specs): ai_video_resources/image-video-director/01-model-registry.md
> Higgsfield CLI names verified via `higgsfield model list` (2026-06-17).

---

## THE RULE: route by SHOT CONTENT, not a default. Match model to what the shot needs.

## CONNECTING SHOTS: by craft, NOT by last-frame handoff

Feeding clip N's last frame into clip N+1 = photocopy-of-a-photocopy → grey mush
(the chain-drift bug). DON'T. Pros re-anchor against drift with the ORIGINAL CLEAN
reference, never the degraded frame (`ai_video_resources/video_model_system_guide.md`
line 418). Connect shots instead by: **match-cut** (shot ends on a shape/motion,
next opens on the matching one — line 510), **shared style/world anchor** repeated
per shot, and **post-assembly** (timeline cut, not inheritance). Cap clips 6-8s
(line 420). Full verdict: `DECISIONS_LOCKED.md` (2026-06-18 fork-resolved section).

---

## VIDEO models (Higgsfield CLI name → best for → cost)

| Need | Model | CLI name | Cost (measured/est) |
|------|-------|----------|------|
| **Fluid / water / physics / lighting realism** | Veo 3.1 | `veo3_1` | ~22cr / 8s basic (MEASURED) |
| **Consistency across shots, chaining, multishot, CHEAP** | Kling 3.0 | `kling3_0` | 7.5cr/5s, 15cr/10s (MEASURED) |
| **Narrative arc, story beats, directorial, ~20s** | Seedance 2.0 | `seedance_2_0` | ~72cr (has genre: epic/horror/noir) |
| **Character/motion realism (benchmarks lead)** | Runway Gen-4.5 | (check list) | — |
| Cheap/volume, declarative prompts | Grok Video 1.5 | `grok_video_v15` | — |
| Also available | Minimax Hailuo, Wan 2.7, Kling 2.6/Turbo | `minimax_hailuo` `wan2_7` `kling3_0_turbo` | — |

Veo params: `--aspect_ratio 9:16 --duration 4/6/8 --quality basic/high/ultra
--image <upload_id>` (i2v needs UPLOADED id via `higgsfield upload create`, NOT a
path — Kling auto-uploads paths, Veo does NOT). model: veo-3-1-fast/preview.

## IMAGE / STILLS models (the photoreal ANCHOR — these looked GOOD, June-14 4/4)

| Need | Model | CLI name |
|------|-------|----------|
| **Photoreal still, high fidelity, reference imgs** | Nano Banana Pro | `nano_banana_2` |
| Photoreal still, fast/cheap, Pro-tier | Nano Banana 2 | `nano_banana_flash` |
| Material realism (subsurface, specular) | Flux 2 | `flux_2` |
| Photoreal via camera/light terms | GPT Image 2 | `gpt_image_2` |
| Text-in-image / typography | Seedream 4.5, Recraft | `seedream_v4_5` `recraft_v4_1` |

(NOTE: CLI label is confusing — `nano_banana_2` displays as "Nano Banana Pro",
`nano_banana_flash` displays as "Nano Banana 2". Trust the CLI name column.)

---

## MEASURED FINDINGS (evidence, not marketing)

- **2026-06-17 — Veo beats Kling on FLUID.** Same pool still + same drain prompt:
  Kling rendered an ugly CGI vortex (cheap); Veo 3.1 rendered real concave water
  funnel w/ surface-tension ripples + refraction (physically real). Registry's
  "Veo = fluid dynamics" claim HELD. → route water/fluid shots to Veo.
- **Stills (nano-banana) look photoreal; Kling VIDEO looked cheap.** The cheap
  look was partly Kling-the-animator + wrong-model-for-content, NOT the writer
  (writer is render-grade, June-14 taxonomy 4/4).

## DEFAULT ROUTING (until more evidence)
- Still anchor: **nano-banana Pro** (`nano_banana_2`).
- Fluid/physics/photoreal motion: **Veo 3.1** (`veo3_1`).
- Need cross-shot consistency / cheap / multishot: **Kling 3.0** (`kling3_0`).
- Spectacle/narrative/epic: **Seedance 2.0** (`seedance_2_0`).
- STATE COST BEFORE RENDER. Veo i2v needs `upload create` first.
