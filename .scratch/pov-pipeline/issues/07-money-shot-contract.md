# 07 — Money-shot contract (pitch-level peak-image capture)

**Status:** closed (shipped 2026-07-17 — schema + pitcher/script prompts + CLI flag +
sheet/checklist; 806 tests green; first live test = kaiju rebuild watch, pending operator
render approval)

## Problem Statement

The operator's imagined video exists only in their head, and no pipeline stage captures it
before money is spent. Proof case (2026-07-17, kaiju rerun): the operator imagined a kaiju
payoff shot — a beam downing the helicopter. The pitch never wrote it down, the script seat
correctly developed only what was written, the render sheet showed what WAS there (not what
was missing from the operator's head), and the gap surfaced only after a 45cr watch:
"where is the COOL beam?" The fix that followed was a hand-edited pitch sentence — a
one-run symptom patch. Every future pitch has the same hole: nothing in the pipeline asks
"what is the money shot?", so "the render missed the thing I imagined" keeps being
discovered at the most expensive gate instead of the cheapest one.

## Solution

Every pitch carries a **money_shot**: the single image the video exists to deliver, stated
as one concrete, camera-pointable sentence. Defined by two operational tests taught to both
LLM seats: the **thumbnail test** (the frame you'd freeze to make someone stop scrolling)
and the **failure test** (if the render nails everything else but misses this, the video
failed anyway). Exactly one per pitch — our format is one 10-15s continuous take, and the
corpus's own action grammar is a ladder of escalating events with ONE peak (sd-067 marks
exactly one moment with its slow-motion ramp). Other big moments are rungs below the peak,
not co-equal money shots; a story with two genuine peaks is two videos.

The operator now judges peaks at the cheapest gate (slate pick / sheet review, zero cost)
instead of the most expensive one (post-render watch, 45cr). The watch checklist's first
question becomes "did the money shot land?" — a falsifiable contract, not a vibe.

## User Stories

1. As the operator, I want every slate pitch to state its money shot, so that I can reject
   a peak-less pitch at pick time for free instead of discovering the gap after a 45cr render.
2. As the operator, I want the slate print to show a money line per pitch, so that
   comparing pitches means comparing their peak images, not just their premises.
3. As the operator, I want the money shot defined by the thumbnail test and the failure
   test, so that the field carries a checkable claim instead of a mood word.
4. As the operator, I want exactly one money shot per pitch, so that the peak stays a peak
   — if everything is a money shot, nothing is.
5. As the operator, I want to pass `--money-shot "<image>"` in idea mode, so that the peak
   I imagine rides into the run byte-verbatim in my own words.
6. As the operator, I want idea mode to still work without `--money-shot`, so that quick
   experiments carry no extra ceremony.
7. As the operator, when I don't state a money shot in idea mode, I want the script stage
   to infer the peak and the sheet to make that inference visible in the beat list, so that
   I can still veto a wrong peak before any spend.
8. As the operator, I want the render sheet to print the money shot verbatim, so that
   gate-2 review checks my imagination against the plan, not just the plan against itself.
9. As the operator, I want "MONEY SHOT LANDS" as the FIRST watch-checklist item, so that
   the 45cr watch verdict starts with the only question that can fail the video on its own.
10. As the operator, I want the script's climax to deliver the pitch's money shot (final
    beat by default, penultimate under a short button that never out-scales it), so that
    the video ends on its largest image instead of deflating past it.
11. As the operator, I want a cliffhanger button after the money shot to stay legal, so
    that endings like "fireball, then jets close in" survive the contract.
12. As the operator, I want the money shot code-copied from pitch to every downstream
    artifact, so that no LLM restatement can drift what I approved.
13. As the operator, I want money-shot misses recorded in the sheet's defect log, so that
    recurrence — not a single miss — is what earns a harder enforcement layer.
14. As the operator, I want the pitcher taught that the money shot may coincide with the
    turn's image but must always be stated as a concrete visual, so that "the twist" can
    never stand in for "the picture".
15. As the operator, I want the archived beam run kept on disk unrendered and marked
    superseded, so that the record stays honest about what was and wasn't watched.
16. As the operator, I want the kaiju story rebuilt through the finished pipeline with its
    money shot stated, so that the first render under this contract is also its first live test.

## Implementation Decisions

- The pitch schema gains a required `money_shot` string. Required, no default — an
  optional field silently reopens the capture gap, the same reasoning that made
  `camera_register` required. Grill decision Q1: the field lives on the PITCH (pitcher
  authors it, operator judges it at pick); it does not live on the script, and the script
  never echoes it back as a trusted field (echo doctrine).
- Both seat system prompts (pitcher and script) carry the same definition text: single
  image the video exists to deliver; thumbnail test; failure test; concrete and
  camera-pointable, never a feeling; may coincide with the turn's visual form but is
  always an image, not a narrative statement.
- Pitcher field spec: every slate pitch states its money_shot. The driver's slate print
  gains a money line per pitch.
- Idea mode (grill Q2): new optional `--money-shot` CLI flag, byte-verbatim into the
  pitch artifact (same code-copy proof as `--idea`). Unset → the existing idea-mode
  placeholder-note convention fills the field, and the script prompt is instructed to
  infer the peak from what_happens + turn; the inference is visible as the script's
  climax beat on the sheet — it is NOT echoed into the pitch field.
- Script craft rule (grill Q3): the money shot is the CLIMAX image — final beat by
  default, penultimate legal when a short button follows, and the button must never
  out-scale it. The existing escalation rule (final beat = largest image) anchors to the
  stated money shot instead of a guess.
- Enforcement (grill Q4): prompt + human gates only. No lexical delivery check (the
  spine-check verdict: lexical checks cannot read prose). No LLM judge seat now; the
  sheet defect log measures money-shot misses, and RECURRENCE promotes enforcement to a
  judge — whack-a-mole policy as ratified.
- The compiler does NOT compile money_shot into the prompt text. The beats deliver the
  image; the field is a contract artifact for the human gates. Compiler and word budget
  are untouched by this feature.
- The bounded-repair loop is unchanged: money-shot misses are not structural violations
  (no code check names them); an operator-flagged miss at the sheet gate is handled by
  the existing re-roll/reword split.
- Render sheet: prints the money shot verbatim in the pitch block; the watch checklist
  gains "MONEY SHOT LANDS" as item 1.
- Pending beam run (grill Q5): archived on disk unrendered, sheet marked superseded; the
  kaiju story is rebuilt through the new pipeline with money_shot stated, and the 45cr
  480p approval is asked fresh on the new sheet.

## Testing Decisions

- External behavior only, on the four seams ratified with the operator (2026-07-17), all
  pre-existing — zero new seams:
  1. Orchestration seam (highest): the pipeline driver + CLI parser with fake seats —
     `--money-shot` flows byte-identical to the pitch artifact and sheet; unset produces
     the placeholder; the slate print carries the money line. Prior art: the existing
     byte-identical code-copy tests in the CLI test module.
  2. Pure-function seam: the render-sheet builder — money shot printed verbatim,
     "MONEY SHOT LANDS" present and first in the checklist. Prior art: the existing
     sheet-element tests.
  3. Seat-contract seam: FakeLLM prompt pins — pitcher and script prompts teach the
     definition (thumbnail/failure tests) and the climax binding. Prior art: the existing
     prompt-teaches tests for both seats.
  4. Schema seam: the pitch model requires money_shot and rejects its absence. Prior
     art: the camera_register required-field tests.
- Whether a rendered clip actually lands its money shot is a HUMAN gate (watch), not a CI
  assertion — same split as every other craft rule in this lane.

## Out of Scope

- An LLM judge seat for money-shot delivery (recurrence-gated future promotion).
- Any lexical/code check that a beat "contains" the money shot (rejected: lexical checks
  cannot read prose).
- Multiple money shots per pitch or a spectacle-beat list (rejected at definition: one
  peak per continuous take; two peaks = two videos).
- A pitcher prompt rule requiring a spectacle payoff act in every action pitch — separate
  candidate already logged on the first kaiju run's sheet, waiting on recurrence.
- Backfilling money_shot into historical run directories.
- Slice ② (IP topics with reference assets).

## Further Notes

- Corpus grounding for the single-peak definition: sd-067 packs several large events but
  marks exactly one climax with "RAMPS TO SLOW MOTION" — the action grammar is an
  escalation ladder with one peak [cited]. The escalation craft rule shipped earlier today
  already demands final-beat-largest; this contract tells it WHICH image that is.
- Disease framing, per the operator's own push (asked three times "symptom or disease?"):
  camera register and escalation rules fixed how the script executes; this fixes what the
  pipeline never captured — the operator's intended peak. It moves the "where is the COOL
  beam?" moment from after-45cr to before-any-spend.
- First live test: the kaiju rebuild (user story 16). Its watch verdict — checklist item 1
  — is the first data point on whether prompt-level delivery holds or the judge-seat
  promotion path starts accumulating evidence.
