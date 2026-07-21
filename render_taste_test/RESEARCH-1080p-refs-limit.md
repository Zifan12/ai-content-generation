# RESEARCH: 1080p × image-refs failure on Seedance 2.0 (Higgsfield) — root cause

Date: 2026-07-20. Question: why does `seedance_2_0` 1080p + 6 image refs fail 4/4
lifetime (opaque server "failed", refunded) while 1080p/no-refs and 480p/720p+refs
complete? Method: web research (firecrawl + exa), official docs + aggregator API
schemas + community, cross-checked against our own billing-verified renders.

## Verdict (HIGH confidence)

**Upstream ByteDance serves the Seedance 2.0 multimodal reference-to-video
pipeline only at 480p/720p. 1080p/4k exist only for the text-to-video /
first-frame task types. Higgsfield's param surface advertises the combo without
validating it, so 1080p+refs jobs die upstream as opaque "failed" + auto-refund.**

Not an account issue. Not transient. Not our prompt. Not fixable by bisecting
duration — refs are the killer variable, confirmed by today's probes (10s and 15s
both fail identically; 1080p/5s/no-refs completes).

## Evidence

1. **[cited] Replicate official `bytedance/seedance-2.0` readme** (the multimodal
   reference product, updated ~2026-06): "Supported resolutions" table lists ONLY
   480p and 720p — and its 480p 9:16 dimensions (496×864) are byte-identical to
   our completed take_480p_roll2.mp4. https://replicate.com/bytedance/seedance-2.0/readme
2. **[cited] AihubMax `seedance-2.0-reference-to-video` OpenAPI spec**: resolution
   enum = `480p`, `720p` (default) — full stop. Same endpoint carries the exact
   9-image / 3-video / 3-audio / 12-total caps Higgsfield's CLI enforces, so this
   IS the upstream contract Higgsfield fronts.
   https://docs.aihubmax.com/pages/en/api-manual/video-series/seedance/seedance-2.0-reference-to-video
3. **[cited] Seedance 1.0-family precedent**: "multi-reference caps at 720p... Using
   1080p with Lite models for reference workflows either triggers an error or falls
   back to 720p silently" (seedance2.so/blog/how-to-use-seedance-2). Same product
   split, one generation earlier.
4. **[cited] BytePlus ModelArk first-party API reference** (docs.byteplus.com
   ModelArk/1520757): resolution notes are per-VARIANT only ("1080p: Not supported
   by Seedance 2.0 Fast and Mini; 4k: Only supported by Seedance 2.0") — no
   task-type restriction documented. First-party MAY expose 1080p ref-to-video;
   every reseller (Replicate, AihubMax, Higgsfield-in-practice) serves refs at
   ≤720p. [inference] Higgsfield's contract matches the reseller tier.
5. **[cited] Higgsfield's own failure taxonomy** (geo.higgsfield.ai blog, 2026-07-07):
   upstream-provider errors are the most common failure class, surface as opaque
   failed generations, credits auto-refunded — matches our 4 failures exactly.
6. **[cited] Higgsfield CLI MODELS.md** (read in full): `seedance_2_0` schema
   allows refs + 1080p/4k with zero combo constraint — the param surface is wrong,
   same class as github.com/higgsfield-ai/cli/issues/49 (params accepted, upstream
   gate rejects).
7. **[measured] Our account**: 1080p/15s/6refs fail ×3, 1080p/10s/6refs fail ×1,
   1080p/5s/0refs complete, 480p/15s/6refs complete, 720p/15s/refs complete
   (pitch-51). All billing-verified.

## What this means for the lane

- **720p is the native ceiling for ANY ref-bound render** (our whole POV lane is
  ref-bound). Stop attempting 1080p+refs; also do NOT burn credits probing
  4k+refs — same pipeline, same cap class. [inference from 1-4]
- **Industry-standard workaround = render 720p native, upscale in post**
  (aiimagetovideo.pro documents "generate 720p, upscale externally" as the common
  pattern). Higgsfield ships `bytedance_video_upscale` / `topaz_video` /
  `video_upscale` job types — our pre-registered 0.3cr bytedance upscale A/B is
  exactly this path.
- Higgsfield "Unlimited" mode caps at 720p anyway; 1080p is a credit-mode-only
  feature for t2v shapes. No plan tier fixes ref-bound 1080p.

## Falsifier / re-check

If Higgsfield or ByteDance later announce 1080p reference-to-video (check
Replicate readme's resolution table first — it tracks upstream), one 45cr
1080p/5s/2refs probe settles it. Until then this is closed.
