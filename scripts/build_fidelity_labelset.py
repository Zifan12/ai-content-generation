"""Build a blinded, labelable fidelity seed set from the per-item eval dump.

THROWAWAY data-prep (build-order step 1 of the fidelity-judge meta-eval; see
`docs/superpowers/specs/2026-06-03-fidelity-judge-meta-eval.md`). Joins the per-item
generation-eval dump to its golden targets by `rank`, blinds the two scripts so the human
labeler cannot see which is RAG vs naked, and emits a labelable JSONL plus a separate
un-blinding key.

Why blinded: the labeler (you) knows RAG is "the horse we bet on." That knowledge biases
the verdict. Shuffling each pair to script_1/script_2 and storing the rag/naked mapping in
a SEPARATE key file keeps the ruler (the labels) uncorrupted. Never open the key while
labeling.

Why only four target fields: the fidelity rubric (spec §4) judges a script's *text* on the
aesthetic/atmosphere mechanics it can actually express — hook_type, primary_emotion,
color_mood, visual_complexity. Engagement mechanics (share/comment bait) and finished-video
properties (audio/loop/duration/pacing) are excluded; see spec §4.3 / §4.4.

Inputs (read utf-8 — the per-item dump has non-cp1252 bytes that crash Windows' default
open()):
  - output/generation_eval_peritem.jsonl   (rank, rag_script, naked_script, ...)
  - data/golden/generation_targets.jsonl   (rank, blueprint_template{...})

Outputs (utf-8, output/ is gitignored — copy the labelable file elsewhere before filling
it in, since this script overwrites on every run):
  - output/fidelity_labelset.jsonl   one row per pair: rank, answer-key mechanics,
                                      script_1, script_2, blank human_preferred/human_reason
  - output/fidelity_key.jsonl        rank -> which slot (script_1/script_2) is rag vs naked

Run:
  $env:PYTHONIOENCODING='utf-8'; .venv\\Scripts\\python.exe -m scripts.build_fidelity_labelset
"""

from __future__ import annotations

import io
import json
import random
from pathlib import Path

PERITEM_PATH = Path("output/generation_eval_peritem.jsonl")
TARGETS_PATH = Path("data/golden/generation_targets.jsonl")
LABELSET_OUT = Path("output/fidelity_labelset.jsonl")
KEY_OUT = Path("output/fidelity_key.jsonl")

# Spec §4.1 — the only target fields a script's text can be judged on.
ANSWER_KEY_FIELDS = ("hook_type", "primary_emotion", "color_mood", "visual_complexity")

# Fixed seed so the blind shuffle is reproducible: a re-run regenerates the SAME
# labelset/key pairing, so labels collected against one run still un-blind correctly.
SHUFFLE_SEED = 20260603


def _read_jsonl(path: Path) -> list[dict]:
    """
    Read a JSONL file as utf-8 and return its rows as a list of dicts.

    utf-8 is forced because the per-item dump contains bytes that Windows' default cp1252
    codec cannot decode (raises UnicodeDecodeError mid-file otherwise).
    """
    with io.open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    """
    Join per-item pairs to their targets by rank, blind the scripts, and write the
    labelable seed set plus the un-blinding key.

    Fails loud (KeyError) if a per-item rank has no matching target, rather than silently
    dropping the pair — a missing target would mean an unlabelable row.
    """
    peritem = _read_jsonl(PERITEM_PATH)
    targets_by_rank = {row["rank"]: row["blueprint_template"] for row in _read_jsonl(TARGETS_PATH)}

    rng = random.Random(SHUFFLE_SEED)
    labelset: list[dict] = []
    key: list[dict] = []

    for row in peritem:
        rank = row["rank"]
        template = targets_by_rank[rank]
        answer_key = {field: template.get(field) for field in ANSWER_KEY_FIELDS}

        # Blind: randomly decide whether rag lands in slot 1 or slot 2.
        rag_in_slot_1 = rng.random() < 0.5
        if rag_in_slot_1:
            script_1, script_2 = row["rag_script"], row["naked_script"]
            slot_1_is, slot_2_is = "rag", "naked"
        else:
            script_1, script_2 = row["naked_script"], row["rag_script"]
            slot_1_is, slot_2_is = "naked", "rag"

        labelset.append(
            {
                "rank": rank,
                "target_mechanics": answer_key,
                "script_1": script_1,
                "script_2": script_2,
                "human_preferred": "",  # fill: "script_1" | "script_2" | "tie"
                "human_reason": "",  # fill: one line — which mechanics each honored
            }
        )
        key.append({"rank": rank, "script_1_is": slot_1_is, "script_2_is": slot_2_is})

    with io.open(LABELSET_OUT, "w", encoding="utf-8") as f:
        for entry in labelset:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    with io.open(KEY_OUT, "w", encoding="utf-8") as f:
        for entry in key:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"wrote {len(labelset)} pairs -> {LABELSET_OUT}")
    print(f"wrote un-blinding key   -> {KEY_OUT}")
    print("COPY the labelset out of output/ before filling it in (output/ is gitignored "
          "and this script overwrites on re-run). Do NOT open the key while labeling.")


if __name__ == "__main__":
    main()
