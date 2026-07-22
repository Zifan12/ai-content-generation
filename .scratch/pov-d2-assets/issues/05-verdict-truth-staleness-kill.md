# 05 — Verdict truth (staleness kill)

**What to build:** The verdict flow always releases what was actually validated. The probe-exemption hash covers the compiled prompt PLUS the ordered reference file list, so swapping a ref invalidates a prior PASS. The released final command carries the run's references as absolute paths at 1080p. Still spend counts toward the 300cr cap. The final log entry names the kept take; re-rolls of a passed prompt never create defect verdicts.

**Blocked by:** 03, 04.

**Status:** ready-for-agent

- [ ] Hash input = compiled prompt + ordered ref file names; ref change → prior PASS no longer exempts
- [ ] Final command includes `--image-references` absolute paths (when the run has refs)
- [ ] Cap tally includes recorded still spend
- [ ] Final log entry supports a kept-take note; no per-take verdicts
- [ ] Old prompt-only hash records need no migration (lookup by new hash simply misses)
- [ ] Driver-level stale-ref scenario test green
