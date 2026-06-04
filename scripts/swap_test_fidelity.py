"""Position-bias confirmation test for the fidelity labels.

THROWAWAY diagnostic. The first labeling pass put 11 of 13 decisive verdicts on whichever
script sat in slot 2 — a position-bias signal (see the meta-eval spec §7). This re-shows a
sample of the *decisive* pairs with the two scripts in FLIPPED slots and records a fresh
verdict, then reports whether each re-judged pick followed the same CONTENT as before
(unbiased) or the same SLOT (biased).

How the comparison works:
- Original pass: `data/golden/fidelity_labels.jsonl` holds human_preferred as a slot
  ("script_1"/"script_2") under the ORIGINAL slotting in `output/fidelity_labelset.jsonl`.
- `output/fidelity_key.jsonl` maps each slot to its content (rag/naked) for that slotting.
- This test displays slot_1 := original script_2 and slot_2 := original script_1 (flipped).
  Your new slot pick is translated back to content via the flip, then compared to the
  content you picked originally.
  - same content  -> consistent (you judged the text, not the position)
  - different content (you again chose by slot) -> position bias confirmed

Only DECISIVE original verdicts are tested (ties carry no directional content to flip).

Run it in YOUR terminal (interactive):
  $env:PYTHONIOENCODING='utf-8'; .venv\\Scripts\\python.exe -m scripts.swap_test_fidelity
Optional:  --n 5  (how many pairs to re-test, default 5)
"""

from __future__ import annotations

import argparse
import io
import json
import random
from pathlib import Path

LABELSET_PATH = Path("output/fidelity_labelset.jsonl")
KEY_PATH = Path("output/fidelity_key.jsonl")
LABELS_PATH = Path("data/golden/fidelity_labels.jsonl")
RESULTS_PATH = Path("output/fidelity_swaptest.jsonl")

DIVIDER = "=" * 78
SUBDIVIDER = "-" * 78
SAMPLE_SEED = 424242
CHOICE_MAP = {"1": "slot_1", "2": "slot_2", "t": "tie"}


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file as utf-8 (script text carries non-cp1252 bytes)."""
    with io.open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _content_of_original_pick(pref_slot: str, key_row: dict) -> str:
    """Translate an ORIGINAL slot verdict ('script_1'/'script_2') to its content (rag/naked)."""
    return key_row[f"{pref_slot}_is"]


def _content_of_swap_pick(swap_slot: str, key_row: dict) -> str:
    """
    Translate a SWAP-test slot pick to content. The display is flipped, so:
      swap slot_1 shows the original script_2  -> content = key_row['script_2_is']
      swap slot_2 shows the original script_1  -> content = key_row['script_1_is']
    """
    original_slot = "script_2" if swap_slot == "slot_1" else "script_1"
    return key_row[f"{original_slot}_is"]


def _show_flipped(pair: dict, idx: int, total: int) -> None:
    """Show one pair with scripts in flipped slots: slot_1 := original script_2, etc."""
    print("\n" + DIVIDER)
    print(f"SWAP-TEST {idx}/{total}   rank={pair['rank']}   (scripts re-ordered)")
    print("TARGET MECHANICS:")
    for field, value in pair["target_mechanics"].items():
        print(f"   {field:18} = {value}")
    print(SUBDIVIDER)
    print("SCRIPT_1:\n")
    print(pair["script_2"])  # flipped on purpose
    print(SUBDIVIDER)
    print("SCRIPT_2:\n")
    print(pair["script_1"])  # flipped on purpose
    print(DIVIDER)


def _prompt() -> str | None:
    """Prompt for a verdict; return stored slot string, 'tie', or None to quit."""
    while True:
        raw = input("Which honored the mechanics better?  [1] script_1  [2] script_2  "
                    "[t] tie  [q] quit : ").strip().lower()
        if raw == "q":
            return None
        if raw in CHOICE_MAP:
            return CHOICE_MAP[raw]
        print("  ? enter one of: 1 2 t q")


def main() -> None:
    """
    Sample N decisive original verdicts, re-judge them flipped, and report content- vs
    slot-consistency so position bias is confirmed or cleared.
    """
    parser = argparse.ArgumentParser(description="Confirm position bias in fidelity labels.")
    parser.add_argument("--n", type=int, default=5)
    args = parser.parse_args()

    pairs_by_rank = {p["rank"]: p for p in _read_jsonl(LABELSET_PATH)}
    key_by_rank = {k["rank"]: k for k in _read_jsonl(KEY_PATH)}
    labels = _read_jsonl(LABELS_PATH)

    decisive = [row for row in labels if row["human_preferred"] in ("script_1", "script_2")]
    if not decisive:
        print("No decisive labels to swap-test.")
        return

    rng = random.Random(SAMPLE_SEED)
    sample = rng.sample(decisive, min(args.n, len(decisive)))

    results: list[dict] = []
    for idx, label in enumerate(sample, start=1):
        rank = label["rank"]
        pair = pairs_by_rank[rank]
        key_row = key_by_rank[rank]

        _show_flipped(pair, idx, len(sample))
        new = _prompt()
        if new is None:
            break
        if new == "tie":
            verdict = {"swap_pref": "tie", "swap_content": "tie"}
            consistent = None
        else:
            swap_content = _content_of_swap_pick(new, key_row)
            orig_content = _content_of_original_pick(label["human_preferred"], key_row)
            verdict = {"swap_pref": new, "swap_content": swap_content}
            consistent = swap_content == orig_content

        results.append(
            {
                "rank": rank,
                "orig_pref_slot": label["human_preferred"],
                "orig_content": _content_of_original_pick(label["human_preferred"], key_row),
                **verdict,
                "content_consistent": consistent,
            }
        )

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with io.open(RESULTS_PATH, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    tested = [r for r in results if r["content_consistent"] is not None]
    consistent = sum(1 for r in tested if r["content_consistent"])
    print("\n" + DIVIDER)
    print(f"SWAP-TEST DONE: {len(results)} re-judged, {len(tested)} decisive both times.")
    if tested:
        print(f"  content-consistent (judged text): {consistent}/{len(tested)}")
        print(f"  slot-followed (position bias):     {len(tested) - consistent}/{len(tested)}")
        print("  -> mostly consistent = clean ruler; mostly slot-followed = bias confirmed, re-label.")
    print(f"results -> {RESULTS_PATH}")


if __name__ == "__main__":
    main()
