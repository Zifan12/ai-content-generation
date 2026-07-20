# Research: 480p→1080p upscale vs native-1080p for platform delivery (2026-07-19)

Question (operator): if we roll keepers at 480p, upscale to 1080p (bytedance_video_upscale,
0.3cr), and upload to TikTok/Shorts — is delivered quality worse than rendering native 1080p
(~9cr/s inferred)? Two-agent research: corpus (video-researcher) + web (general-purpose).
Full agent outputs: session 2026-07-19 evening; key citations inline.

## The one decisive finding

**The upscale-vs-native gap is SCENARIO-DEPENDENT, and our register sits in the worst
scenario class.** Practitioner Seedance tests split: 480p+Topaz→1080p "indistinguishable for
the most part" on static/simple content (4 blind comparisons, creator switched to save 75%
credits) [youtube QN76FmK7loU]; native clearly wins on FAST MOTION and LOW LIGHT — "you can
definitely tell it was upscaled" [youtube GAw24jfTbPA, JSFILMZ]; gap "reopens on fast motion,
fine text, complex particle effects" [mindstudio.ai]. POV action register = hyper-chaotic
handheld + dusk + beam particle VFX = all three named native-wins conditions at once.

## Supporting facts

- **No one has run the post-platform A/B** (upload both, compare delivered). EVIDENCE THIN —
  the literal question is unanswered publicly. Must self-test.
- TikTok measured transcode: ~30.9 Mbps source → ~2.5 Mbps delivered (~88% cut), downsampled
  ~715×1270, HQ toggle OFF (UC Denver thesis, Waddell Dec 2025). Compression is heaviest on
  fast motion — platform crush may COMPOUND the upscale gap there, not mask it. [inference]
- YT Shorts runs its own undisclosed ML "enhance" pass on some Shorts (Aug 2025 backlash,
  opt-out promised) — a confound on any Shorts-side A/B. [arstechnica]
- Seedance 1.0's "native 1080p" was itself cascaded (480p base + jointly-TRAINED diffusion
  refiner, arXiv:2506.09113) — architecture fact for 1.0 only, unverified for 2.x. A trained
  refiner ≠ generic post-hoc upscaler; does not license the cheap path by analogy.
- bytedance_video_upscale (Higgsfield) = likely hosted SeedVR/SeedVR2 wrap [inference,
  unconfirmed]. SeedVR2 reputation: strong on AI footage, beats Topaz on face texture
  (freckle preservation, fal.ai comparison); artifact classes = plastic/waxy oversharpening,
  tile-seam grids on faces (GitHub #542/#528), banding on 7B model.
- Corpus (governing docs): the 480p→720p→1080p ladder is NATIVE REGENERATION per tier
  (credit discipline, methodology/15:288-298); render-low-then-upscale as finals strategy
  appears nowhere in our lane's docs; output-side upscale sanctioned only as targeted defect
  patch (Topaz face-softening fix, guide:443). Whether generation resolution changes DRAWN
  detail (not just pixels): UNCOVERED in corpus.

## Verdict (pending our own watch)

Theory + practitioner evidence lean **native 1080p for finals in THIS register** (fast
motion/low light/particles). But the deciding instrument is the operator's eyes post-platform:

1. Watch the existing upscaled-1080p first keeper (bytedance upscale, pending watch).
2. Next native-1080p keeper (already planned) = the native side of the A/B.
3. Upload both as private drafts, watch on-device, decide. Zero extra render cost.

Decision entry goes to DECISIONS_LOCKED.md only after the on-device A/B watch.
