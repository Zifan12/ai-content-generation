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

## UPDATE 2026-07-21 — the cap DOES NOT hold when a VIDEO reference is present [measured, n=1]

The verdict above was derived and measured entirely on IMAGE-reference-only jobs.
On 2026-07-21 a render with a `--video-references` clip added (spacium-pose motion
transfer) + 4 image refs **COMPLETED at native 1080p**, billing-verified charged
(NOT refunded):

- **Job 7af7931d** (`seedance_2_0`, 1080p, 15s, 9:16, `mode std`): 1× video_reference
  (`refs/motion/spacium_pose_ref.mp4`) + 4× image_references (ultraman crops).
  Status `completed`, **135cr spend, no refund** (`higgsfield account transactions`).
  Output: `output/pov/20260719_235242_*/.../motiontransfer_native1080p_7af7931d.mp4`
  (also saved under the 20260721_154010 run dir).
- Contrast: image-refs-ONLY at 1080p failed **0/5+ lifetime** (jobs 09602490, 9e1ed0d5,
  045099b7, 3483b499 + the bisect probes) — the evidence base for the cap above.

**Best-fit reading (consistent with the original verdict, not a contradiction of it):**
the original finding is that 1080p exists for **t2v / first-frame task types**, and
the multimodal **image-ref-to-video** path is 480p/720p only. Adding a video reference
very likely re-routes the job into a task type that DOES carry 1080p — so "1080p +
refs" was never a flat ban, it was specifically "1080p + IMAGE-ref-to-video." The
video-ref path is a different pipeline.

**Confidence: n=1, billing-verified but unconfirmed.** Alternative explanation not
yet excluded: the eligibility gate is non-deterministic (documented elsewhere) and
this was one lucky pass — though a single pass on a NEW config after 0/5+ on the old
config points to a real config difference, not variance.

**Confirm step (cheap):** re-run the exact 7af7931d config once. A second completion
promotes this to a lane rule; a failure reopens the non-determinism question. If
confirmed: **native 1080p is available for video-ref renders** — and since our register
(fast motion / particles) is exactly where native beats upscale
(RESEARCH-upscale-vs-native.md), native-1080p-with-video-ref becomes the finals path
for any POV keeper that uses a motion reference, NOT the 3cr upscale.

**A/B now on disk** (the post-platform test RESEARCH-upscale-vs-native.md said was
missing — same content, both 1080p): `motiontransfer_native1080p_7af7931d.mp4` (135cr)
vs `motiontransfer_1080p_upscaled.mp4` (3cr pro bytedance upscale of the 480p base).
Operator watch pending — judges whether the 132cr native premium is visible on our
register.
