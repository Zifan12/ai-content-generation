# 01 — Native-1080p ladder + cap 300

**What to build:** After a probe PASS the operator receives a native **1080p ×1** final command (not 720p, never an upscale); the sheet documents the corrected ladder (480p probe → watch → native 1080p final, upscaler = draft salvage only) and carries a 720p fallback line for the known 1080p+image-refs rejection risk. The per-story credit cap rises 150→300 (config value), and the rate table gains the still-generation cost row so later slices can tally image spend.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Probe-PASS verdict releases a final command at 1080p, one take
- [ ] Sheet ladder text: probe → watch → native 1080p ×1; upscaler demoted to draft-salvage; second take = logged override
- [ ] Final release includes the 720p-fallback guidance line
- [ ] Cap enforced at 300 (config value, evidence note updated)
- [ ] GPT Image 2 still cost row present in the rate table (measured ~7cr, 2026-07-22)
- [ ] Existing verdict/driver tests updated and green
