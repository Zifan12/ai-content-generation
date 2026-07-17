"""
Probe: re-render pitch-51 with the three FREE defect fixes applied by hand.

WHY THIS EXISTS:
  The user watched the pitch-51 paid render (67.5cr, 2026-07-16) and named four
  defects. Three have a candidate text fix; one does not. This probe applies the
  three text fixes to pitch-51's EXACT composed prompt — everything else stays
  byte-identical (same 5 reference images, same model, same duration) — so ONE
  480p render tells us which of the three theories are real, for 45cr.

  This is patch-to-test, not patch-to-ship. The prompt this script builds is
  throwaway; the KNOWLEDGE of which fixes worked is the deliverable. Only after a
  fix is proven here does it earn a permanent home in the pipeline (the system
  cure is designed in docs/superpowers/specs/2026-07-16-pitcher-room-ownership.md
  and deliberately NOT built yet — building it first would be curing an untested
  theory).

THE FOUR DEFECTS AND WHAT THIS PROBE DOES ABOUT EACH:

  1. "The opening makes no sense / the escape crawl is hidden."
     Cause: the pitcher chose shot_size=extreme_close_up on a HAND, so the crawl
     toward the door is never visible. The director obeyed faithfully.
     FIX A (here): open wide, show the man dragging himself toward the door.

  2. "Elfaria talks to camera."
     Cause (corrected 2026-07-16 by corpus research — the earlier attribution to
     the ref asset was WRONG): the prompt never wrote a gaze clause at all. It
     wrote a CAMERA move ("slow tilt up ... to her face") and no subject-gaze
     action. Corpus is convergent (kling-masterclass L601-603, happyhorse L107-112,
     image-video-director/03 L92): gaze is a SUBJECT ACTION ("looks down at him"),
     controlled by its own clause, never by camera phrasing. With nothing written,
     the render fell back on the ref's camera-facing eyeline.
     FIX B (here): write the gaze clause.
     NOT fixed here: her SMILE (the ref smiles; neutral expression is mandatory per
     reference-material-playbook.md:59-60 + the vendor's "无表情最佳"). That needs a
     regenerated ref, which costs image credits — a separate, deliberate decision.
     Note the corpus PRESCRIBES a camera-facing eyeline on an identity ref
     (Dan Kieft L512/L518), so the new ref must change the EXPRESSION ONLY, never
     the gaze.

  3. "Two doors."
     Cause: the composed prompt asserted two contradicting FROZEN states next to
     each other — world_anchor's "the heavy wooden door is on the far wall" (which
     matches room.jpg: one door, CLOSED) and the story's "the open doorway" (which
     does not). Seedance drew both. Corpus note: a state CHANGE from a reference is
     legitimate and intended ("the door swings open"); pitch-51 never wrote a
     change, it asserted a second static state.
     FIX C (here): delete "open doorway" entirely. The only door language left is
     the anchor's, which agrees with the photo.
     Also removed: "from the open doorway on the far wall" as a CAMERA POSITION.
     "far wall" is egocentric — true only from where the room photo was shot — so
     using it to place a reverse-angle camera inverts every direction in the anchor.

  4. "The lift teleports."
     NOT FIXED. Seedance will not animate one body lifting another off the floor.
     Probe-disproven 2026-07-16 (45cr): a dedicated shot + an explicit
     follow-the-rise camera cue did not help; the rise still rendered in ZERO
     frames. BUG-031. Accepted as a model limit.

DELIBERATELY NOT CHANGED (would confound the test):
  - The text still says "candlelight" in three shots while room.jpg is broad
    daylight. This is the SAME contradiction class as the door and is wrong by the
    2026-07-16 design decision ("the photo owns the light"). But no lighting defect
    was reported, so changing it would add a variable. If the render comes back with
    strange light, pull this thread next.
  - world_anchor stays at its current 50 words (its generator asks for 15-20;
    a layout paragraph was hand-appended). Trimming it tests a DIFFERENT theory.

USAGE:
  uv run python scripts/probe_pitch51_patched.py              # dry run, prints cost, spends nothing
  uv run python scripts/probe_pitch51_patched.py --confirm    # renders, 45cr at 480p/15s

  Then WATCH THE VIDEO. Do not judge it from sampled frames — that error was made
  on 2026-07-16 and the user's own eyes corrected a "total failure" verdict to
  "partial success". Frames measure; the user judges.

DISCARD AFTER:
  Throwaway probe for one render. Delete once the three theories are answered.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv("config/.env")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.generation.executor import execute_scene  # noqa: E402
from src.generation.render_adapters.schemas import RenderJob  # noqa: E402

SOURCE = "output/smoke_runs/smoke_20260716_002107_2899ec1.json"
OUT_DIR = "output/smoke_runs/probe_pitch51_patched_480p"

# FIX D — the smile. Both of Elfaria's refs smile with eyes on the lens; the render
# reproduced the smile over the prompt's "smirk" (refs beat prompts). Neutral expression
# is mandatory in three independent sources: reference-material-playbook.md:59-60,
# video_model_system_guide.md:444, and the 火山方舟 vendor PDF ("无表情最佳" / no expression
# is best) via 08-避坑12问.md:17.
#
# BOTH refs must swap together, never one. Swapping only the headshot would leave a
# SMILING full-body ref beside a NEUTRAL headshot — the documented conflicting-reference
# averaging failure: "If one image is smiling and another is neutral, the model creates a
# 'midpoint face' that looks like neither" (video_model_system_guide.md:398). That would
# damage identity, not repair expression.
#
# The GAZE is deliberately unchanged. The corpus PRESCRIBES a camera-facing eyeline on an
# identity ref ("eyes looking straight into the camera lens", Dan Kieft L512/L518); the
# camera-stare defect is fixed in TEXT by FIX B, not by averting the ref's eyes.
REF_SWAPS = {
    "refs\\elfaria_albis_serfort\\master.png": "refs/elfaria_albis_serfort/master_neutral.png",
    "refs\\elfaria_albis_serfort\\sheet_identity.png": "refs/elfaria_albis_serfort/sheet_identity_neutral.png",
}

# (label, exact source text, replacement). Each is asserted present before replacing:
# a silent no-op would render the ORIGINAL prompt and burn 45cr proving nothing.
PATCHES = [
    (
        "FIX A: open wide so the escape crawl is visible (was a close-up of a hand)",
        "Extreme close-up, low angle. Will Serfort's trembling hand claws weakly at the floor "
        "just inside the open doorway, his fingers scraping with each convulsion,",
        "Wide shot. Will Serfort lies collapsed on the floor near the heavy wooden door, dragging "
        "himself toward it, his trembling arm reaching out and clawing weakly at the floor as he "
        "pulls himself forward,",
    ),
    (
        "FIX A2: follow the man, not the hand",
        "Camera: slow push-in toward his hand.",
        "Camera: slow push-in.",
    ),
    (
        "FIX C: drop the second door + the egocentric camera position",
        "Wide shot, from the open doorway on the far wall. Still gripping",
        "Wide shot. Still gripping",
    ),
    (
        "FIX B: write the gaze as a subject action (the prompt never said where she looks)",
        "His head lolls onto her shoulder. A satisfied smirk curls her lips as she says, "
        "'Zeo was mistaken. This is where you belong.'",
        "His head lolls onto her shoulder. She looks down at his face, never at the camera, "
        "a satisfied smirk curling her lips as she says to him, "
        "'Zeo was mistaken. This is where you belong.'",
    ),
]


def build_patched_job() -> RenderJob:
    """Load pitch-51's exact render job and apply the three text fixes.

    Everything except the prompt string is carried over untouched — same
    reference_images (all 5, same order: positional ref binding matters), same
    model, aspect ratio, and covers_shots. Only the prose changes, so a
    difference in the render is attributable to the prose.

    Raises:
        AssertionError: if any patch's source text is not found verbatim, or if
            "open doorway" survives. Failing loud here costs nothing; failing
            silently costs 45 credits and produces a result that means nothing.
    """
    data = json.loads(Path(SOURCE).read_text(encoding="utf-8"))
    job_data = dict(data["render_jobs"][0])
    prompt = job_data["prompt"]

    for label, old, new in PATCHES:
        assert old in prompt, f"patch anchor NOT FOUND -> {label}\nlooked for: {old[:70]}..."
        prompt = prompt.replace(old, new)
        print(f"  [applied] {label}")

    assert "open doorway" not in prompt, "'open doorway' survived the patch"
    assert "toward his hand" not in prompt, "hand-follow camera survived the patch"
    assert "looks down at his face" in prompt, "gaze clause missing"

    # FIX D — swap BOTH of Elfaria's refs to their neutral-expression edits, in place, so
    # positional ref binding (image1..image5 in the prompt) is preserved exactly.
    refs = list(job_data["reference_images"])
    swapped = 0
    for i, ref in enumerate(refs):
        if ref in REF_SWAPS:
            new_ref = REF_SWAPS[ref]
            assert Path(new_ref).exists(), f"neutral ref missing on disk: {new_ref}"
            refs[i] = new_ref
            swapped += 1
            print(f"  [applied] FIX D: ref {i + 1} -> {Path(new_ref).name}")
    assert swapped == len(REF_SWAPS), (
        f"expected to swap {len(REF_SWAPS)} refs, swapped {swapped} — a partial swap leaves "
        "a smiling ref beside a neutral one and averages them into a midpoint face"
    )
    job_data["reference_images"] = refs

    job_data["prompt"] = prompt
    return RenderJob(**job_data)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument(
        "--confirm",
        action="store_true",
        help="Actually render (spends credits). Without this, dry-run only.",
    )
    ap.add_argument("--resolution", default="480p", help="480p (default, cheapest) | 720p | 1080p")
    args = ap.parse_args()

    print("Patching pitch-51's composed prompt:")
    job = build_patched_job()
    print(f"\nrefs (unchanged, {len(job.reference_images)}): {[Path(r).name for r in job.reference_images]}")
    print(f"model: {job.model_cli_id} | duration: {job.duration}s | {args.resolution}")

    est = execute_scene(job, OUT_DIR, resolution=args.resolution, dry_run=True)
    print(f"\nESTIMATED COST: {est.credits_spent} credits")

    if not args.confirm:
        print("\nDRY RUN — nothing spent. Re-run with --confirm to render.")
        print(f"Patched prompt saved to {OUT_DIR}/prompt.txt for review.")
        Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
        Path(OUT_DIR, "prompt.txt").write_text(job.prompt, encoding="utf-8")
        return

    result = execute_scene(job, OUT_DIR, resolution=args.resolution)
    print(f"\nDone. {result}")
    print(f"\nWATCH THE VIDEO: {OUT_DIR}/take_1.mp4")
    print("Judge it with your eyes, not with frame stats. Three questions:")
    print("  1. Can you tell he's crawling for the door?")
    print("  2. Is there ONE door?")
    print("  3. Does she look at HIM instead of the camera?")


if __name__ == "__main__":
    main()
