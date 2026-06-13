"""
THROWAWAY smoke test for ContentWriter.write() (P3 Task 5).

Runs write() once per premise in PREMISES (4 stratified what-if premises, one
per axis: creature / environment / transformation / scale) against real DB rows
+ a real Sonnet call each, and prints a human-readable arc dump per premise for
eyeballing against the 4-failure rubric. Not an eval, not a gate — just "does it
produce coherent chained takes across premises, and where does it fail". Delete
after use.

Stratifying across 4 premises (not 1) is deliberate: a single premise cannot
reveal whether the writer overfits one template — only a spread exposes
cross-premise monotony.

Picks the most common niche among v3 blueprints, uses 3 of those blueprints as
the retrieved "winners" (hits), hand-builds a plausible target candidate from
the first one's grouped mechanics, and asks the writer to generate around each
premise.
"""

import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load secrets BEFORE importing src.database (it reads DATABASE_URL at import).
load_dotenv("config/.env")

from sqlalchemy import select  # noqa: E402

from src.database import SessionLocal  # noqa: E402
from src.models.blueprint import BlueprintRecord  # noqa: E402
from src.miner.schemas import BlueprintCandidate, MinerEvidence  # noqa: E402
from src.rag.schemas import RetrievalHit  # noqa: E402
from src.generation.content_writer import ContentWriter  # noqa: E402

PREMISES = [
    "Footage of Kraken appearing in the pacific ocean",
    "POV: Someone exploring and found the Yggdrasil",
    "Human transforming into an angel",
    "Life as an ant"
]


class _Tee:
    """
    Duplicate every write to two streams (live console + the record file).

    The smoke prints to stdout for live eyeballing; wrapping sys.stdout in a _Tee
    for the duration of the run also captures the EXACT same text to a timestamped
    transcript so runs can be diffed against each other later (regression hunting).
    Only write/flush are needed — print() touches nothing else.
    """

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)

    def flush(self):
        for s in self._streams:
            s.flush()


def _git_sha() -> str:
    """
    Return the current short git SHA, or "nogit" if unavailable.

    Stamped into every transcript header so a saved smoke run is traceable to the
    exact prompt/schema commit that produced it — a transcript you cannot tie to a
    code version is uncomparable.
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "nogit"


def main() -> None:
    # Open a timestamped, SHA-stamped transcript and tee all stdout into it.
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sha = _git_sha()
    record_path = Path("output/smoke_runs") / f"smoke_{ts}_{sha}.txt"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_file = record_path.open("w", encoding="utf-8")
    record_file.write(f"# smoke_content_writer run\n# timestamp: {ts}\n# git_sha: {sha}\n\n")
    record_file.flush()

    original_stdout = sys.stdout
    sys.stdout = _Tee(original_stdout, record_file)

    db = SessionLocal()
    try:
        v3 = db.scalars(
            select(BlueprintRecord).where(BlueprintRecord.extractor_version == "v3")
        ).all()
        if len(v3) < 3:
            raise SystemExit(f"Need >=3 v3 blueprints, found {len(v3)}.")

        niches = Counter(b.blueprint_data.get("niche_label", "unknown") for b in v3)
        top_niche, _ = niches.most_common(1)[0]
        print(f"niche distribution (v3): {niches.most_common()}")
        print(f"using niche: {top_niche}\n")

        chosen = [b for b in v3 if b.blueprint_data.get("niche_label") == top_niche][:3]

        hits = [
            RetrievalHit(
                content_item_id=b.content_item_id,
                blueprint_id=b.id,
                score=0.90 - i * 0.05,
                blueprint_data=b.blueprint_data,
                niche_label=b.blueprint_data.get("niche_label", "unknown"),
            )
            for i, b in enumerate(chosen)
        ]

        # Hand-build a target candidate from the first winner's grouped mechanics.
        seed = chosen[0].blueprint_data
        template = {
            k: seed[k]
            for k in ("hook_type", "pacing", "audio_type")
            if k in seed
        }
        candidate = BlueprintCandidate(
            rank=1,
            niche_label=top_niche,
            blueprint_template=template,
            evidence=MinerEvidence(
                matching_items=len(chosen),
                median_views=250_000,
                p90_views=1_200_000,
                trend_slope_4wk_pct=12.5,
                rationale="smoke-test synthetic evidence",
            ),
        )
        print(f"candidate template: {template}")
        print(f"hit content_item_ids: {[h.content_item_id for h in hits]}\n")

        writer = ContentWriter()

        chosen_devices: list[str] = []

        slot_labels = ("OPENING", "MIDDLE", "CLOSING")

        for premise in PREMISES:
            package = writer.write(candidate, hits, db, premise)
            chosen_devices.append(package.device)

            # Human-readable arc dump — surface only the fields the rubric needs
            # (3 labeled chained segments + the package mood-anchor + overlays +
            # caption). Skip braces/hashtags/grounding_ids/rationale: noise for the
            # read. mood_anchor is package-level (one grade for the whole take), so
            # it prints once.
            print("=" * 70)
            print(f"PREMISE: {premise}")
            print(f"DEVICE: {package.device}  —  {package.device_rationale}")
            print(f"MOOD-ANCHOR: {package.mood_anchor}")
            print("-" * 70)
            for slot, shot in zip(slot_labels, package.shots):
                # start_keyframe prints only on segment 1 (the only generated still);
                # segments 2-3 inherit the prior clip's last frame. end_keyframe
                # printed even when absent (as a marker) so the read shows which
                # segments reach a target state vs ride pure motion.
                start = shot.start_keyframe if shot.start_keyframe is not None else "— (inherits prior clip's last frame)"
                end = shot.end_keyframe if shot.end_keyframe is not None else "— (no end-state)"
                print(f"[{slot}]")
                print(f"  START:  {start}")
                print(f"  MOTION: {shot.motion}")
                print(f"  END:    {end}\n")
            print(f"OVERLAYS: {package.onscreen_text}")
            print(f"CAPTION:  {package.caption}")
            print("=" * 70 + "\n")

        # Cross-premise device-variety check — the anti-monotony guard being
        # exercised. A single premise cannot reveal a template; only the spread can.
        # If all 4 premises collapse to one device, the writer is defaulting to a
        # habit instead of letting the premise drive the pick — that is the monotony
        # failure resurfacing, so shout it. This is a printed diagnostic for the
        # human, not an assertion.
        distinct = set(chosen_devices)
        print("#" * 70)
        print(f"DEVICE PICKS (in premise order): {chosen_devices}")
        print(f"DISTINCT DEVICES: {sorted(distinct)}  ({len(distinct)} of {len(chosen_devices)})")
        if len(distinct) == 1:
            print(">>> MONOTONY WARNING: all premises chose the same device. "
                  "The pick is not tracking the premise — iterate the prompt.")
        print("#" * 70)

    finally:
        db.close()
        sys.stdout = original_stdout
        record_file.close()
        print(f"\n[record saved] {record_path}")


if __name__ == "__main__":
    main()
