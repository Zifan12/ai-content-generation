"""Interactive terminal helper for hand-labeling the fidelity seed set.

THROWAWAY labeling UI (build-order step 2 of the fidelity-judge meta-eval; see
`docs/superpowers/specs/2026-06-03-fidelity-judge-meta-eval.md`). Walks the blinded pairs
produced by `scripts/build_fidelity_labelset.py` one at a time, shows each row's four target
mechanics + the two blinded scripts, and records which script better honored those
mechanics. Writes verdicts to a separate, persistent labels file so the run is resumable
and the source labelset stays pristine.

Blinding is preserved: this tool reads only `script_1` / `script_2` from the labelset and
NEVER touches `fidelity_key.jsonl`. The labeler cannot tell rag from naked.

You (the human) run this in YOUR terminal — it uses input() and is interactive. Do NOT run
it through a non-interactive harness.

Inputs:
  --labelset  (default output/fidelity_labelset.jsonl)  the blinded pairs to label.
  --labels    (default data/golden/fidelity_labels.jsonl)  where verdicts persist; if it
              already exists, its verdicts are loaded and those ranks are skipped (resume).

Output: the --labels JSONL, one row per labeled pair:
  {"rank", "target_mechanics", "human_preferred": "script_1"|"script_2"|"tie",
   "human_reason": "..."}

Run:
  $env:PYTHONIOENCODING='utf-8'; .venv\\Scripts\\python.exe -m scripts.label_fidelity
  (add  --labels data\\golden\\fidelity_labels.jsonl  to choose a different verdicts file)
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

DIVIDER = "=" * 78
SUBDIVIDER = "-" * 78

# Keypress -> stored verdict value.
CHOICE_MAP = {"1": "script_1", "2": "script_2", "t": "tie"}


def _read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file as utf-8 (the labelset carries non-cp1252 bytes)."""
    with io.open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    """Write rows to a JSONL file as utf-8, preserving non-ASCII script text."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _show_pair(row: dict, done: int, total: int) -> None:
    """
    Print one pair for labeling: the four target mechanics (the answer key) followed by the
    two blinded scripts in full. Nothing here reveals which script is rag vs naked.
    """
    print("\n" + DIVIDER)
    print(f"PAIR rank={row['rank']}   ({done} labeled / {total} total)")
    print("TARGET MECHANICS (judge fidelity against these):")
    for field, value in row["target_mechanics"].items():
        print(f"   {field:18} = {value}")
    print(SUBDIVIDER)
    print("SCRIPT_1:\n")
    print(row["script_1"])
    print(SUBDIVIDER)
    print("SCRIPT_2:\n")
    print(row["script_2"])
    print(DIVIDER)


def _prompt_choice() -> str | None:
    """
    Prompt for a verdict. Returns the stored verdict string ("script_1"/"script_2"/"tie"),
    or None if the labeler chose to quit. Skips ('s') return the sentinel "__skip__".

    Re-prompts on any unrecognized key rather than recording a bad label.
    """
    while True:
        raw = input("Which honored the mechanics better?  [1] script_1  [2] script_2  "
                    "[t] tie  [s] skip  [q] quit+save : ").strip().lower()
        if raw == "q":
            return None
        if raw == "s":
            return "__skip__"
        if raw in CHOICE_MAP:
            return CHOICE_MAP[raw]
        print("  ? enter one of: 1 2 t s q")


def main() -> None:
    """
    Drive the labeling loop: load the blinded labelset, skip ranks already in the labels
    file (resume), and for each remaining pair record a verdict + one-line reason. Saves
    after every verdict so quitting never loses progress.
    """
    parser = argparse.ArgumentParser(description="Hand-label the fidelity seed set.")
    parser.add_argument("--labelset", type=Path, default=Path("output/fidelity_labelset.jsonl"))
    parser.add_argument("--labels", type=Path, default=Path("data/golden/fidelity_labels.jsonl"))
    args = parser.parse_args()

    pairs = _read_jsonl(args.labelset)
    labeled = _read_jsonl(args.labels) if args.labels.exists() else []
    done_ranks = {row["rank"] for row in labeled}

    remaining = [p for p in pairs if p["rank"] not in done_ranks]
    if not remaining:
        print(f"All {len(pairs)} pairs already labeled in {args.labels}. Nothing to do.")
        return

    print(f"{len(labeled)} already labeled, {len(remaining)} to go. "
          "Type q at any prompt to save and stop.")

    for pair in remaining:
        _show_pair(pair, done=len(labeled), total=len(pairs))
        choice = _prompt_choice()
        if choice is None:
            break
        if choice == "__skip__":
            continue
        reason = input("One-line reason (which mechanics each hit/missed): ").strip()
        labeled.append(
            {
                "rank": pair["rank"],
                "target_mechanics": pair["target_mechanics"],
                "human_preferred": choice,
                "human_reason": reason,
            }
        )
        _write_jsonl(args.labels, labeled)
        print(f"  saved. ({len(labeled)}/{len(pairs)})")

    print(f"\nStopped. {len(labeled)}/{len(pairs)} labeled -> {args.labels}")


if __name__ == "__main__":
    main()
