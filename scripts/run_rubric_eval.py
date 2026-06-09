"""
THROWAWAY P3 driver: run the writer-rubric v0 (code-check tier) scorecard.

Generates real ContentPackages from the live Sonnet writer, then runs the
deterministic rubric scorecard over them and prints per-criterion pass-rates
plus every failure receipt. This is the first time the rubric meets REAL writer
output (the pytest suite only scores hand-crafted packages); it is the evidence
the Task 5 gate reads to decide whether the v1 LLM-judge tier is worth building.

Unlike scripts.run_generation_eval (the heavy grounded RAG gate), this driver is
DB-free and GPU-free: it uses the NAKED envelope (target template only, no
retrieved winners), so no Postgres, no embedder, no reranker. The rubric checks
are mechanical (scale comparisons, palette-in-keyframe, quality incantations,
mood-anchor identity, ...) and do not depend on grounding — only on the writer's
own text — so the naked path is enough to exercise them.

Every generated package is also dumped to a timestamped JSONL under
output/rubric_eval/ so a later rubric edit can be re-scored for FREE via
--rescore, without paying for generation again.

MODES
  (default)        generate over the 4 stratified smoke premises, then score
  --all            generate over the 20 golden targets instead of the premises
  --rescore PATH   skip generation entirely; load packages from a prior JSONL
                   dump and score them (no LLM calls, no cost)

COST / PREREQS (read before running)
  - default: 4 Sonnet calls. --all: 20 Sonnet calls. --rescore: zero.
  - config/.env must hold ANTHROPIC_API_KEY (loaded below before any src import).
  - No database or GPU required.

Run:
    $env:PYTHONIOENCODING='utf-8'
    .venv\\Scripts\\python.exe -m scripts.run_rubric_eval
    .venv\\Scripts\\python.exe -m scripts.run_rubric_eval --all
    .venv\\Scripts\\python.exe -m scripts.run_rubric_eval --rescore output/rubric_eval/packages_20260607_210000.jsonl
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load secrets BEFORE importing anything that may read keys at import time.
load_dotenv("config/.env")

from src.providers.llm.anthropic_llm import AnthropicLLM  # noqa: E402
from src.schemas.generation import ContentPackage  # noqa: E402
from src.generation.content_writer import SYSTEM_PROMPT, build_naked_envelope  # noqa: E402
from src.miner.schemas import BlueprintCandidate, MinerEvidence  # noqa: E402
from src.evals.rubric_eval import scorecard  # noqa: E402

WRITER_MODEL = "claude-sonnet-4-6"
GOLDEN_PATH = Path("data/golden/generation_targets.jsonl")
DUMP_DIR = Path("output/rubric_eval")
# A full 3-shot package overruns the 1024 default; give the parse room so a long
# montage is not truncated into a schema-parse failure.
MAX_TOKENS = 2048

# Four stratified what-if premises, one per axis (creature / environment /
# transformation / scale) — the same spread scripts.smoke_content_writer uses, so
# the scorecard sees varied structures (different organizing_principles), not one
# template repeated. A single premise cannot reveal cross-premise mechanical habits.
PREMISES = [
    "Footage of Kraken appearing in the pacific ocean",
    "POV: Someone exploring and found the Yggdrasil",
    "Human transforming into an angel",
    "Life as an ant",
]


def synthetic_candidate() -> BlueprintCandidate:
    """
    Build one ungrounded target candidate with a minimal, plausible mechanic
    template — no DB row needed.

    The naked envelope carries only blueprint_template, and the mechanical rubric
    checks never read the evidence stats, so the evidence fields are filled with
    synthetic-but-valid numbers purely to satisfy the BlueprintCandidate schema.
    The template names a few grouped mechanics so the writer has a HOW to honor
    while the premise supplies the WHAT.
    """
    return BlueprintCandidate(
        rank=1,
        niche_label="surreal_hyperreal",
        blueprint_template={
            "hook_type": "impossible_reveal",
            "pacing": "slow_atmospheric",
            "audio_type": "ambient_drone",
        },
        evidence=MinerEvidence(
            matching_items=3,
            median_views=250_000,
            p90_views=1_200_000,
            trend_slope_4wk_pct=12.5,
            rationale="synthetic evidence for the rubric driver (not from the miner)",
        ),
    )


def premise_envelope(premise: str, candidate: BlueprintCandidate) -> str:
    """
    Compose a naked user envelope that still carries a premise.

    Mirrors the head of content_writer.build_envelope (premise first, then the
    target template) but appends NO winner blocks — the ungrounded control shape
    with the premise restored, so each of the 4 premises drives its own topic
    while sharing one synthetic template.
    """
    template = build_naked_envelope(candidate)
    return f"Premise:\n{premise}\n\nTarget Blueprint:\n{template}"


def load_golden(path: Path) -> list[BlueprintCandidate]:
    """
    Read the golden generation targets JSONL into BlueprintCandidate objects, in
    file order. Same fixture and loader shape as scripts.run_generation_eval.
    """
    candidates = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            candidates.append(BlueprintCandidate.model_validate(json.loads(line)))
    return candidates


def generate(llm: AnthropicLLM, envelopes: list[str]) -> list[ContentPackage]:
    """
    Run the writer's structured-output call once per envelope and collect the
    validated ContentPackages, printing a progress line per call.

    Each call uses the real SYSTEM_PROMPT so the packages are faithful writer
    output; only the grounding (retrieved winners) is omitted.
    """
    packages = []
    for i, envelope in enumerate(envelopes, 1):
        print(f"  generating {i}/{len(envelopes)} ...", flush=True)
        package = llm.parse(envelope, ContentPackage, system=SYSTEM_PROMPT, max_tokens=MAX_TOKENS)
        packages.append(package)
    return packages


def dump_packages(packages: list[ContentPackage]) -> Path:
    """
    Persist every generated package to a timestamped JSONL under output/rubric_eval/
    so a later rubric edit can be re-scored for free via --rescore. Returns the path.
    """
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DUMP_DIR / f"packages_{ts}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for package in packages:
            f.write(package.model_dump_json() + "\n")
    return path


def load_packages(path: Path) -> list[ContentPackage]:
    """Load ContentPackages from a prior --rescore JSONL dump, in file order."""
    packages = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            packages.append(ContentPackage.model_validate_json(line))
    return packages


def print_scorecard(rates: dict, failures: list) -> None:
    """
    Print the scorecard: per-criterion pass-rates (worst first, so the rules most
    in need of a prompt fix surface at the top) and every failure receipt.
    """
    print("\n" + "=" * 70)
    print("RUBRIC v0 SCORECARD")
    print("=" * 70)
    print("\nPASS-RATE BY CRITERION (worst first):")
    for criterion_id, rate in sorted(rates.items(), key=lambda kv: kv[1]):
        print(f"  {rate:6.0%}  {criterion_id}")

    print(f"\nFAILURES ({len(failures)}):")
    if not failures:
        print("  none — every applied criterion passed on every package")
    else:
        for receipt in failures:
            print(f"  [{receipt.criterion_id}] {receipt.reason}")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the writer-rubric v0 scorecard.")
    parser.add_argument("--all", action="store_true",
                        help="generate over the 20 golden targets instead of the 4 smoke premises")
    parser.add_argument("--rescore", metavar="PATH",
                        help="score packages from a prior JSONL dump; no generation, no cost")
    args = parser.parse_args()

    if args.rescore:
        packages = load_packages(Path(args.rescore))
        print(f"Re-scoring {len(packages)} packages from {args.rescore} (no LLM calls).")
        rates, failures = scorecard(packages)
        print_scorecard(rates, failures)
        return

    llm = AnthropicLLM(model=WRITER_MODEL)

    if args.all:
        candidates = load_golden(GOLDEN_PATH)
        print(f"Loaded {len(candidates)} golden targets from {GOLDEN_PATH}.")
        envelopes = [build_naked_envelope(c) for c in candidates]
    else:
        candidate = synthetic_candidate()
        print(f"Using {len(PREMISES)} smoke premises with one synthetic target template.")
        envelopes = [premise_envelope(p, candidate) for p in PREMISES]

    print(f"Generating {len(envelopes)} packages via {WRITER_MODEL} (naked, no grounding)...")
    packages = generate(llm, envelopes)

    dump_path = dump_packages(packages)
    print(f"\n[packages saved] {dump_path}  (re-score later with --rescore {dump_path})")

    rates, failures = scorecard(packages)
    print_scorecard(rates, failures)


if __name__ == "__main__":
    main()
