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

**Status:** CLOSED — check rejected on measured evidence (user call, 2026-07-15). See verdict at the bottom.

- [ ] A director line missing the beat's `destination` fails or repairs — it never reaches the package silently.
- [ ] A director line missing the beat's `required_action` fails or repairs.
- [ ] A director line containing both passes untouched, and craft the director added that the pitch never mentioned is preserved — elevation is not clipped.
- [ ] A beat with `destination: None` skips the destination check, does not raise, and logs the skip.
- [ ] A legacy pitch with no spine fields still renders end-to-end, with skips logged.
- [ ] `shot_size` is copied from the beat and survives even when the director's draft echoes a different one — mirroring the existing "copied from pitch not draft" tests.
- [ ] The pitch-47 regression exists as a test: given its real beats and a director line that says "across the room", the check catches it.
- [ ] **Free validation:** re-run the writer on pitch 47 and diff the shipped line against `visual_line`. The bed and the lift are present. Record the diff.
- [~] `uv run pytest`, `uv run ruff check .`, `uv run mypy src/` — same true-and-precise status as ticket
  03's line (see there): zero regressions, changed files clean on all three, and the repo's standing
  numbers unchanged — `pytest` 2 pre-existing failures (BUG-028 + the flaky rag latency test), `ruff`
  34, `mypy` 17. Not "all pass"; that phrasing was wrong on 03 and is not repeated here.

**After this ticket — read before rendering.** The free diff proves the story reached the *prompt*. It does
NOT prove it reaches the *screen*: in pitch 47, "she looks down with a cool, satisfied smirk" **was** in the
shipped prompt and the render still inverted the register. This work fixes narrative only — pacing has no
lever in the single-generation lane, and motion is unknown. Before any paid render, fix the turnaround-sheet
references (see `project_multiview_refs_worsen_id_drift`) or the render is confounded like every one before it.


---

## VERDICT (2026-07-15) — the check was built, measured, and rejected. The bug is fixed anyway.

**User decision: skip the check.** Not deferred — rejected on evidence. Full reasoning and the numbers
live in `PRD.md` under "D2/D3 ARE REJECTED"; the short version:

**The check does not work, and it fails in both directions at once.** The director is REQUIRED to
paraphrase — that is the elevation this whole PRD protects. Lexically, a synonym ("chest" -> "shoulder",
"grasping" -> "grips") is indistinguishable from a dropped fact: both are just *different words*. Measured
on real output from pitches 50 and 51:

- The destination check FALSE-FAILED good writing (`destination="Elfaria's chest"`; director shipped
  "cradling him; his head lolls against her **shoulder**" — the cradle is right there).
- The same check PASSES pitch 47's actual bug line, because "head lolling against Elfaria's chest"
  literally contains the word "chest".
- Which way it lands depends on which noun the pitcher happened to pick: it chose `"the bed"` for that
  beat on pitch 48 (check works) and `"Elfaria's chest"` on pitches 50 AND 51 (check inverts).
- `required_action` overlap: clean-spine floor **0.62** vs the real bug at **0.42** — +0.03 of margin.

**The bug does not reproduce.** Two live runs post-02/03 both shipped the bed AND the lift. Pitch 51 beat
2, verbatim: *"...drags him across the floor; his fingers leave shallow trails on the stone as he slides
back **toward the bed**."* Pitch 51 beat 3: *"**lifts** Will Serfort by the wrist and pulls his limp body
**onto the bed**, cradling him."* Tickets 02 and 03 fixed it. This ticket was a burglar alarm for a
break-in that had already stopped, and the alarm went off at the mailman.

**Checklist disposition:**
- [x] **Free validation** — DONE, and it PASSES WITHOUT THE CHECK. Not on pitch 47: that pitch predates
  ticket 02 and has NO spine fields (`beats_with_spine=0`), so the check would have skipped every beat
  and validated nothing. Ran on pitch 50 (first pitch with a full spine) and pitch 51. Diffs recorded in
  `output/pitch50_director.json` / `output/pitch51_director.json`.
- [x] The pitch-47 regression exists as a test — as the STRUCTURAL guarantee, which is the checkable one:
  `test_director_sees_each_beats_own_story_not_a_paraphrase` pins that the director gets each beat's own
  visual_line/destination/required_action with no paraphrase hop between it and the pitch. Reintroduce a
  PLAN-like stage and it fails. It cannot pin that the LLM honors what it reads — live runs evidence that.
- [~] `shot_size` code-copy (D5) — **dropped, different reason.** Nothing reads it: grep of `src/` finds
  `shot_size` only in `StoryBeat`, its variety validator, and prompt prose — absent from
  `src/schemas/generation.py`, the adapter, and the executor. Copying it into `ShotSpec` adds a field no
  consumer reads, and the only way to make it bite is to validate framing prose against the enum, which is
  the same lexical disease. It is already enforced where it always was: the director prompt's FRAMING clause.
- [x] Expression stops leaking into the spine — done as the prerequisite the user chose (commit `67c8320`),
  and verified live: repitch 50 -> 51 came back pure motion on all 4 beats.
- [ ] ~~destination/required_action assertions~~ — rejected, see above.
- [ ] ~~`destination: None` skips loudly~~ — moot without the check.

**Accepted cost, stated plainly:** if this failure class returns in a new form, nothing catches it
automatically. It gets caught by watching the render, as it was the first time. That is the price of not
having a check that works, and it was taken knowingly.

**Still true, and still the next gate before any paid render:** fix the turnaround-sheet references
(`project_multiview_refs_worsen_id_drift`) or the render is confounded like every one before it.
