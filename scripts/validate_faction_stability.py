"""Build-time faction-map shuffle-stability validation harness (Exilus PRD ticket 08).

Answers the question the Exilus redesign exists to answer: does the faction-map
reader (``src/monitor/faction_reader.py``, ticket 05) actually fix the
cross-run instability that killed the old single-consensus gap read
(``src/monitor/gap_agent.py`` -- "the same Reddit thread was re-read into six
different 'consensus' summaries across runs"), or does it just repaint the
same non-determinism under a new schema?

This is a one-time, PAID, MANUAL, NOT-CI validation of the faction-reader
PROMPT, not a runtime safeguard (PRD "Out of Scope": "Runtime stability
double-rolls of the faction read (build-time validation only)"). It takes
2-3 real Reddit threads (comment sets already filtered by the existing
>=5-upvote floor -- the same filter production input already passed through,
see ``src/monitor/tools/reddit_search.py``'s ``_MIN_COMMENT_SCORE``), produces
shuffled and/or subsampled variants of each thread, runs the faction-map
reader independently on every variant, and prints a camp-by-camp comparison
report. It computes NO automated pass/fail verdict -- per repo convention
(and this ticket's explicit ACs), whether "the same camps re-emerged" is a
judgment only the user makes reading the report.

Input path: one ``--file`` per thread, each file a plain-text dump of
already-tagged, already-floor-filtered comment lines (the exact
``[COMMENT | N upvotes] ...`` shape ``reddit_search.py`` / ``ContextAgentState
.reddit_text`` already produce -- copy them straight out of a real run).
There is deliberately no fridge-read path: ``WebResearchChunk`` rows chunk web
text AND Reddit text through the same chunker with no source-kind marker
(ticket 04's documented tradeoff), so reconstructing one thread's *exact*
comment set from fridge chunks is not reliable -- a plain file dump is the
honest seam for "the real, floor-filtered comment set" this ticket's AC1
requires.

Cost/correctness note: the ``FactionReader`` built here is wired with a
no-op ``item_fetcher`` (returns no items). Without it, a variant that dips
below the ~30-comment floor (a very likely outcome once shuffled/subsampled)
would trigger ``FactionReader.read``'s real top-up ``reddit_search`` call --
an unbudgeted extra Apify spend the user did not consent to per-variant, AND
a way for a comment absent from the original floor-filtered set to sneak
into a variant, which would break this harness's own "no comment introduced
that wasn't in the original set" contract (AC1). The no-op fetcher makes
every below-floor variant simply THIN DATA-stamped instead, which is itself
useful validation signal (does thin data still find stable camps?).
"""

import argparse
import random
import subprocess
from pathlib import Path

from src.monitor.schemas import FactionMap


def git_sha() -> str:
    """
    Return short git SHA of HEAD, or "unknown" if git unavailable or call fails.

    Reused verbatim from ``scripts/run_pitch_ablation.py`` (pure-ops
    boilerplate, per this ticket's "Who types" section).
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def load_comments(path: Path) -> list[str]:
    """Read one thread's floor-filtered comment dump: one tagged comment per line.

    Blank lines are ignored. Every non-blank line is treated as one atomic
    comment unit for shuffling/subsampling -- callers should pass a file
    containing only comment lines already known to have survived the
    ``_MIN_COMMENT_SCORE = 5`` floor (e.g. lines copied straight out of a
    real ``reddit_search`` / ``ContextAgentState.reddit_text`` dump).
    """
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def make_variants(
    comments: list[str],
    n_variants: int = 3,
    drop_fraction: float = 0.0,
    seed: int | None = None,
) -> list[list[str]]:
    """Produce ``n_variants`` shuffled (and optionally subsampled) copies of ``comments``.

    Pure, no LLM/network call (AC4) -- this is the harness's own
    variant-generation control flow, exercisable in a unit test against a
    fixed fake comment list. Each variant is an independent random
    permutation of the FULL ``comments`` list; when ``drop_fraction`` > 0,
    each variant additionally keeps only the first
    ``round(len(comments) * (1 - drop_fraction))`` entries of its own
    shuffle -- a random subset, never a comment absent from the original
    list (AC1: "no comment introduced that wasn't in the original
    floor-passing set"). ``drop_fraction=0.0`` (the default) produces pure
    shuffles with every comment kept -- the PRD allows "shuffled and/or
    subsampled," and shuffling alone already exercises the order-sensitivity
    question this harness exists to probe; pass a positive ``drop_fraction``
    to additionally probe volume-sensitivity.

    Args:
        comments: The thread's full floor-filtered comment list.
        n_variants: How many independent variants to produce.
        drop_fraction: Fraction (0.0-1.0) of comments to randomly omit per
            variant.
        seed: Seed for the shared ``random.Random`` instance driving every
            variant's shuffle -- set it for a reproducible run; each variant
            still gets its own distinct permutation (the seed determines the
            whole batch's sequence, not one repeated shuffle).

    Returns:
        A list of ``n_variants`` comment lists, each a shuffled (and
        possibly subsampled) view of ``comments``.
    """
    rng = random.Random(seed)
    keep_n = (
        max(1, round(len(comments) * (1 - drop_fraction))) if comments else 0
    )
    variants = []
    for _ in range(n_variants):
        shuffled = list(comments)
        rng.shuffle(shuffled)
        variants.append(shuffled[:keep_n])
    return variants


def run_stability_validation(
    faction_reader,
    threads: dict[str, list[str]],
    n_variants: int = 3,
    drop_fraction: float = 0.0,
    seed: int | None = None,
) -> dict[str, list[FactionMap | None]]:
    """Run ``faction_reader.read`` independently over every variant of every thread.

    Threads are processed independently -- each gets its own
    ``make_variants`` call over only its own comments, so no thread's
    variants or resulting camps ever leak into another thread's entry in
    the returned dict.

    Per-variant isolation (mirrors ``run_pitch_ablation.py``'s per-event
    try/except): a variant call that raises (a transient API error, a
    validator reject) is recorded as ``None`` in its slot rather than
    aborting the whole run -- an operator paying for
    ``len(threads) * n_variants`` calls should not lose every
    already-paid-for result because one call failed.

    Args:
        faction_reader: Anything with ``read(topic: str, reddit_text: str)
            -> FactionMap`` (the real ``FactionReader`` in production, a fake
            in tests).
        threads: Thread name -> that thread's full floor-filtered comment
            list.
        n_variants: Variants per thread (PRD default: 3).
        drop_fraction: Passed through to ``make_variants``.
        seed: Passed through to ``make_variants``.

    Returns:
        Thread name -> list of ``n_variants`` ``FactionMap | None`` results,
        in the same order the variants were generated. No camp-count
        normalization or capping happens here beyond what
        ``faction_reader.read`` itself already applied.
    """
    results: dict[str, list[FactionMap | None]] = {}
    for thread_name, comments in threads.items():
        variants = make_variants(comments, n_variants, drop_fraction, seed)
        maps: list[FactionMap | None] = []
        for variant_comments in variants:
            reddit_text = "\n".join(variant_comments)
            try:
                maps.append(faction_reader.read(thread_name, reddit_text))
            except Exception as e:
                print(f"  [{thread_name}] variant failed, skipping: {e}")
                maps.append(None)
        results[thread_name] = maps
    return results


def format_report(results: dict[str, list[FactionMap | None]]) -> str:
    """Render the camp-by-camp comparison report for human judgment (AC3).

    Deliberately computes no pass/fail verdict and applies no camp-count
    normalization: a variant with 1 camp and a variant with 5+ camps both
    print exactly as many camps as they carry. Whether the same camps
    re-emerged across a thread's variants is left entirely to the user
    reading this text.
    """
    lines: list[str] = []
    for thread_name, maps in results.items():
        lines.append("=" * 70)
        lines.append(f"THREAD: {thread_name}")
        lines.append("=" * 70)
        for i, fmap in enumerate(maps, start=1):
            if fmap is None:
                lines.append(f"\n  variant {i}: FAILED (see log above)")
                continue
            thin = " [THIN DATA]" if fmap.thin_data else ""
            lines.append(f"\n  variant {i} -- {len(fmap.camps)} camp(s){thin}")
            for camp in fmap.camps:
                lines.append(
                    f"    - {camp.name} (weight={camp.weight:.2f}, feeling={camp.feeling})"
                )
                lines.append(f"      surface_want:  {camp.surface_want}")
                lines.append(f"      deeper_desire: {camp.deeper_desire} [INFERRED]")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    """CLI entrypoint.

    States the LLM-call cost (``len(threads) * n_variants``) before any
    paid faction-reader call and requires an explicit y/N confirmation
    (repo convention: state cost before spend). Never imported or invoked by
    the test suite or any CI configuration (AC6) -- this function is the
    only place that touches a real LLM, and ``pytest``'s ``testpaths`` is
    scoped to ``tests/`` only (``pyproject.toml``), so this script is never
    auto-collected.
    """
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

    parser = argparse.ArgumentParser(
        description="Build-time shuffle-stability validation of the faction-map "
        "reader prompt (Exilus PRD ticket 08). LIVE SPEND: one faction-reader "
        "LLM call per thread x variant."
    )
    parser.add_argument(
        "--file",
        action="append",
        required=True,
        dest="files",
        help="Path to one thread's floor-filtered comment dump (one tagged "
        "comment per line). Pass 2-3 times, once per thread.",
    )
    parser.add_argument(
        "--variants", type=int, default=3, help="Variants per thread (default 3)."
    )
    parser.add_argument(
        "--drop-fraction",
        type=float,
        default=0.0,
        help="Fraction of each thread's comments to randomly drop per variant "
        "(subsampling); 0.0 (default) = pure shuffle, nothing dropped.",
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="Random seed for reproducible variants."
    )
    args = parser.parse_args()

    threads = {Path(f).stem: load_comments(Path(f)) for f in args.files}
    for name, comments in threads.items():
        print(f"  thread {name!r}: {len(comments)} comments loaded")

    n_calls = len(threads) * args.variants
    print(
        f"\nLIVE SPEND: this run will make {n_calls} faction-reader LLM call(s) "
        f"({len(threads)} thread(s) x {args.variants} variant(s)). git SHA: {git_sha()}"
    )
    if input("Proceed? [y/N]: ").strip().lower() != "y":
        print("Aborted -- no calls made.")
        return

    from src.monitor.faction_reader import FactionReader
    from src.providers.llm.factory import llm_for_seat

    # ponytail: no-op item_fetcher -- see module docstring's "Cost/correctness
    # note." A below-floor variant is a real, wanted outcome to observe
    # (THIN DATA stability), not a trigger for an unbudgeted top-up Apify call.
    faction_reader = FactionReader(
        llm=llm_for_seat("faction_reader"), item_fetcher=lambda run_input: []
    )
    results = run_stability_validation(
        faction_reader,
        threads,
        n_variants=args.variants,
        drop_fraction=args.drop_fraction,
        seed=args.seed,
    )
    print("\n" + format_report(results))


if __name__ == "__main__":
    main()
