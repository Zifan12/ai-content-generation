# 04 — Code enforces the spine and copies shot_size

**What to build:** The bug closes here. A director line that drops the beat's destination or its required
action does not reach a render — code catches it. And the framing the pitch chose is copied from the beat
rather than trusted to the director's echo of it.

After this ticket, re-running the writer on pitch 47 produces a shipped line that contains **the bed** and
**the lift**. That is the whole point of the feature, and it costs zero credits to verify.

**Why code and not a prompt (user decision, 2026-07-15):** the original failure was prompt *adherence*.
PLAN was told "ONE subject action", it obeyed, and obeying is what dropped the lift. Adding another
instruction ("...but never drop a destination") puts two rules in direct tension and lets the LLM referee —
the exact failure mode being eliminated. A prompt is what failed; only code guarantees the property.

**This mirrors an existing, deliberate pattern.** `beat_role`, `characters_in_frame`, `dialogue_line`, and
`speaker` are already copied from the beat under the comment *"code copies the pitch's own beat facts...
rather than trusting the draft's echo of them."* The story and the framing are the beat facts that never
got that treatment. This extends the existing principle rather than inventing a mechanism — find that
copy site and follow it.

**The skip must be loud.** When `required_action` or `destination` is None (a legacy pitch predating 02),
the check skips — and **logs that it skipped**. A guarantee that quietly does nothing on old rows is the
same class of silent no-op that caused this entire investigation.

**Failure behaviour is the implementer's call**, but state it and test it: either raise, or retry the
director once with feedback naming the dropped fact. The existing word-budget repair loop is prior art for
the retry shape, and reusing it is preferred over inventing a second repair mechanism.

**Blocked by:** 02 (the spine fields must exist to check against) and 03 (the check lives in the merged
director's output path).

**Status:** ready-for-agent

- [ ] A director line missing the beat's `destination` fails or repairs — it never reaches the package silently.
- [ ] A director line missing the beat's `required_action` fails or repairs.
- [ ] A director line containing both passes untouched, and craft the director added that the pitch never mentioned is preserved — elevation is not clipped.
- [ ] A beat with `destination: None` skips the destination check, does not raise, and logs the skip.
- [ ] A legacy pitch with no spine fields still renders end-to-end, with skips logged.
- [ ] `shot_size` is copied from the beat and survives even when the director's draft echoes a different one — mirroring the existing "copied from pitch not draft" tests.
- [ ] The pitch-47 regression exists as a test: given its real beats and a director line that says "across the room", the check catches it.
- [ ] **Free validation:** re-run the writer on pitch 47 and diff the shipped line against `visual_line`. The bed and the lift are present. Record the diff.
- [ ] `uv run pytest`, `uv run ruff check .`, `uv run mypy src/` all pass.

**After this ticket — read before rendering.** The free diff proves the story reached the *prompt*. It does
NOT prove it reaches the *screen*: in pitch 47, "she looks down with a cool, satisfied smirk" **was** in the
shipped prompt and the render still inverted the register. This work fixes narrative only — pacing has no
lever in the single-generation lane, and motion is unknown. Before any paid render, fix the turnaround-sheet
references (see `project_multiview_refs_worsen_id_drift`) or the render is confounded like every one before it.
