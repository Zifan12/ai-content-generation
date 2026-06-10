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
  --judge          v1 LLM-judge tier: score each package on the 4 anchored
                   rubric dimensions via WriterJudge (Opus), then print the
                   mean-score scorecard, low-score receipts, and the
                   principle_distribution monotony readout. Combine with
                   --rescore to judge a saved smoke dump (pay judge calls only,
                   not generation). NOT compatible with --all: golden targets
                   carry no premise, and the judge needs premise + package.

COST / PREREQS (read before running)
  - default: 4 Sonnet calls. --all: 20 Sonnet calls. --rescore: zero.
  - --judge is NOT free (unlike v0 --rescore): one Opus call per package
    (4 packages = 4 Opus calls). The anchored rubric rides in the system
    prompt with 1h cache_control, so back-to-back calls reuse the cached
    prefix instead of paying full input price each time.
  - --judge --rescore re-pairs dumped packages with the 4 smoke PREMISES by
    order — only valid for dumps produced by the default (4-premise) mode.
  - config/.env must hold ANTHROPIC_API_KEY (loaded below before any src import).
  - No database or GPU required.

Run:
    $env:PYTHONIOENCODING='utf-8'
    .venv\\Scripts\\python.exe -m scripts.run_rubric_eval
    .venv\\Scripts\\python.exe -m scripts.run_rubric_eval --all
    .venv\\Scripts\\python.exe -m scripts.run_rubric_eval --rescore output/rubric_eval/packages_20260607_210000.jsonl
    .venv\\Scripts\\python.exe -m scripts.run_rubric_eval --judge --rescore output/rubric_eval/packages_20260607_210000.jsonl
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
from src.evals.rubric_eval import scorecard, judge_scorecard, principle_distribution  # noqa: E402
from src.evals.writer_judge import WriterJudge, PackageVerdict  # noqa: E402
from src.evals.package_view import render_for_judge  # noqa: E402

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


def judge_packages(packages: list[ContentPackage], premises: list[str]) -> list[PackageVerdict]:
    """
    Run WriterJudge.judge over each (premise, package) pair, printing a progress
    line per call. PAID: one Opus call per package — there is no free path here.

    Raises SystemExit with a clear message when the package count does not match
    the premise count (e.g. a --all golden dump, which carries no premises).
    """
    if len(packages) != len(premises):
        raise SystemExit(
            f"--judge needs one premise per package: got {len(packages)} packages "
            f"vs {len(premises)} smoke premises. Only dumps from the default "
            f"(4-premise) mode can be judged — --all golden dumps carry no premise."
        )

    judge = WriterJudge()
    verdicts = []
    for i, (premise, package) in enumerate(zip(premises, packages), 1):
        print(f"  judging {i}/{len(packages)} (Opus) ...", flush=True)
        verdicts.append(judge.judge(premise, package))
    return verdicts


def dump_verdicts(
    packages: list[ContentPackage],
    premises: list[str],
    verdicts: list[PackageVerdict],
    source: str,
) -> Path:
    """
    Persist every judge verdict to a timestamped Markdown doc under
    output/rubric_eval/ so the PAID Opus reasons survive the run and can be
    sanity-read against the exact brief the judge saw. Returns the path.

    Judging has no free --rescore path (unlike v0 scoring), so without this dump
    the only copy of the reasons is the terminal scroll-back — re-reading them
    would mean paying for the calls again.

    Each package section carries: the premise, every dimension's score + reason,
    and the verbatim render_for_judge brief — the reasons cite specific brief
    text, so the brief must sit next to them to be checkable.

    Args:
        packages: the judged ContentPackages, in judge order.
        premises: one premise per package, same order.
        verdicts: one PackageVerdict per package, same order.
        source: where the packages came from (dump path or "fresh generation"),
            recorded in the doc header for provenance.
    """
    DUMP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = DUMP_DIR / f"verdicts_{ts}.md"

    lines = [
        "# Writer-judge verdicts (rubric v1)",
        "",
        f"- Judged at: {ts}",
        f"- Packages from: {source}",
        "- Judge: Opus via WriterJudge, anchored 1-5 rubric",
        "",
    ]
    for i, (premise, package, verdict) in enumerate(zip(premises, packages, verdicts), 1):
        lines.append(f"## Package {i}: {premise}")
        lines.append("")
        lines.append("### Scores")
        lines.append("")
        for ds in verdict.scores:
            lines.append(f"- **{ds.dimension} = {ds.score}** — {ds.reason}")
        lines.append("")
        lines.append("### Brief (verbatim, as the judge saw it)")
        lines.append("")
        lines.append("```text")
        lines.append(render_for_judge(premise, package))
        lines.append("```")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def print_judge_scorecard(means: dict, low_scores: list, distribution: dict) -> None:
    """
    Print the v1 judge scorecard: per-dimension mean scores (worst first), every
    low-score receipt with the judge's reason, and the organizing_principle
    distribution (the run-level monotony alarm the per-package judge cannot see).
    """
    print("\n" + "=" * 70)
    print("RUBRIC v1 JUDGE SCORECARD (Opus, anchored 1-5)")
    print("=" * 70)
    print("\nMEAN SCORE BY DIMENSION (worst first):")
    for dimension, mean in sorted(means.items(), key=lambda kv: kv[1]):
        print(f"  {mean:4.2f}  {dimension}")

    print(f"\nLOW SCORES (<= 2) ({len(low_scores)}):")
    if not low_scores:
        print("  none — no dimension scored 2 or below on any package")
    else:
        for ds in low_scores:
            print(f"  [{ds.dimension} = {ds.score}] {ds.reason}")

    print("\nORGANIZING-PRINCIPLE DISTRIBUTION (monotony check):")
    for principle, count in sorted(distribution.items(), key=lambda kv: -kv[1]):
        print(f"  {count}x  {principle}")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the writer-rubric v0 scorecard.")
    parser.add_argument("--all", action="store_true",
                        help="generate over the 20 golden targets instead of the 4 smoke premises")
    parser.add_argument("--rescore", metavar="PATH",
                        help="score packages from a prior JSONL dump; no generation, no cost")
    parser.add_argument("--judge", action="store_true",
                        help="v1 LLM-judge tier: one PAID Opus call per package; "
                             "combine with --rescore to skip generation cost")
    args = parser.parse_args()

    if args.judge and args.all:
        raise SystemExit("--judge does not support --all: golden targets carry no premise.")

    if args.rescore:
        packages = load_packages(Path(args.rescore))
        if args.judge:
            print(f"Judging {len(packages)} packages from {args.rescore} "
                  f"({len(packages)} PAID Opus calls; generation is free, judging is not).")
            verdicts = judge_packages(packages, PREMISES)
            verdict_path = dump_verdicts(packages, PREMISES, verdicts, source=args.rescore)
            print(f"\n[verdicts saved] {verdict_path}")
            means, low_scores = judge_scorecard(verdicts)
            print_judge_scorecard(means, low_scores, principle_distribution(packages))
            return
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

    if args.judge:
        verdicts = judge_packages(packages, PREMISES)
        verdict_path = dump_verdicts(packages, PREMISES, verdicts, source=str(dump_path))
        print(f"\n[verdicts saved] {verdict_path}")
        means, low_scores = judge_scorecard(verdicts)
        print_judge_scorecard(means, low_scores, principle_distribution(packages))
        return

    rates, failures = scorecard(packages)
    print_scorecard(rates, failures)


if __name__ == "__main__":
    main()
