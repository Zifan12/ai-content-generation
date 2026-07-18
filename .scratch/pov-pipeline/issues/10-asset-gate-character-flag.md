# 10 — Asset gate + --character flag

**What to build:** The operator can declare canon subjects on the POV driver
(`--character <slug>` or `--character <slug>:<role>`, repeatable; roles: protagonist
[default], in_frame). When a declared character's reference directory is missing or
invalid, the run halts BEFORE any LLM spend and prints a role-specific REQUEST SHEET
telling the operator exactly which images to supply (per the locked ref format spec —
crops-of-what-camera-sees for protagonist, one-face-region mask close-up + full-body for
in_frame, non-photographic official art, one design version). When references validate,
the run proceeds and the render sheet's copy-paste CLI command carries one `--image` flag
per reference in deterministic order (protagonist refs first — upload order defines
imageN for ticket 11's binding clause). The reference directory is the permanent
per-character library: a repeat subject passes the gate with zero re-work.

Validation is code-checks only (file count within role bounds, readable image files,
declared slug matches a directory) — no LLM judge, per house rule.

**Blocked by:** None — request-sheet content is research-locked, not probe-dependent.

**Status:** ready-for-agent

- [ ] Declared character with no reference directory → request sheet printed naming the
      role-specific images required, run halts, zero LLM calls made (fake seat records
      no calls)
- [ ] Declared character with a valid reference directory → run proceeds; every
      reference path appears as a `--image` flag in the sheet's CLI command, order
      deterministic and documented
- [ ] Reference count outside role bounds, unknown role tag, or non-image file → loud
      named error, no run directory written
- [ ] No `--character` flag → behavior byte-identical to slice ① (zero-ref path
      untouched)
- [ ] Both seams covered: driver-with-fake-seats and compiler-as-pure-function
