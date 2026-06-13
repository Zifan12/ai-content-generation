"""
Wire the v0 rubric criteria into a registry and aggregate them into a scorecard.

`scorer` runs the selected criteria over one package; `scorecard` tallies many
packages into per-criterion pass-rates plus the flat list of failure receipts.
"""

from src.evals.rubric_checks import (
    no_scale_comparison,
    no_quality_incantations,
    no_palette_in_keyframes,
    no_style_words_in_motion,
    device_requires_event_beat,
)
import statistics
from collections import defaultdict, Counter
from src.evals.rubric import select, load
from src.evals.writer_judge import PackageVerdict
from src.schemas.generation import ContentPackage

registry = {
    "no_scale_comparison": no_scale_comparison,
    "no_quality_incantations": no_quality_incantations,
    "no_palette_in_keyframes": no_palette_in_keyframes,
    "no_style_words_in_motion": no_style_words_in_motion,
    "device_requires_event_beat": device_requires_event_beat,
}


def scorer(package: ContentPackage) -> list:
    """Run every criterion the selector picks for this package, returning their CheckResult receipts."""
    criterias = select(package, load())

    result = []
    for criteria in criterias:
        result.append(registry[criteria["id"]](package))

    return result

def scorecard(packages: list[ContentPackage]) -> tuple:
    """
    Aggregate criteria across many packages.

    Returns (rates, failures): rates maps criterion_id -> pass-rate (0-1); failures
    is the flat list of failing CheckResult receipts.
    """
    tally = defaultdict(list)
    failures = []

    for package in packages:
        results = scorer(package)
        for result in results:
            tally[result.criterion_id].append(result)
            if result.passed is False:
                failures.append(result)

    rates = {}
    for criterion_id, bin_results in tally.items():
        total = len(bin_results)
        passes = sum(b.passed is True for b in bin_results)
        rates[criterion_id] = passes / total

    return rates, failures

def judge_scorecard(verdicts: list[PackageVerdict]) -> tuple:
    """
    Aggregate LLM-judge verdicts across many packages.

    Returns (means, low_scores): means maps dimension -> mean score (1-5)
    across all verdicts; low_scores is the flat list of DimensionScore
    receipts with score <= 2, kept whole so the judge's `reason` rides
    along for failure inspection.
    """
    tally = defaultdict(list)
    low_scores = []

    for verdict in verdicts:
        for dim_score in verdict.scores:
            tally[dim_score.dimension].append(dim_score)
            if dim_score.score <= 2:
                low_scores.append(dim_score)

    means = {}
    for dim_str, dim_scores in tally.items():
        means[dim_str] = statistics.mean([d.score for d in dim_scores])

    return means, low_scores


def device_distribution(packages: list[ContentPackage]) -> dict:
    """
    Tally the chosen device across many packages — the run-level monotony alarm.

    Each package carries exactly one `device` (the closed 7-menu pick); counting
    them across a run surfaces the failure no per-package check can see: the writer
    collapsing every premise onto one device (the trap-default habit). Returns a
    Counter mapping device -> number of packages that chose it.
    """
    devices = [p.device for p in packages]
    return Counter(devices)
