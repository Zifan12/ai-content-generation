from src.evals.rubric_checks import (
    mood_anchor_identical,
    no_scale_comparison,
    no_quality_incantations,
    no_palette_in_start_keyframe,
    no_style_words_in_transition,
    escalating_wrongness_has_event_beat,
)

from collections import defaultdict
from src.evals.rubric import select, load
from src.schemas.generation import ContentPackage

registry = {
    "mood_anchor_identical": mood_anchor_identical,
    "no_scale_comparison": no_scale_comparison,
    "no_quality_incantations": no_quality_incantations,
    "no_palette_in_start_keyframe": no_palette_in_start_keyframe,
    "no_style_words_in_transition": no_style_words_in_transition,
    "escalating_wrongness_has_event_beat": escalating_wrongness_has_event_beat,
}


def scorer(package: ContentPackage) -> list:
    criterias = select(package, load())

    result = []
    for criteria in criterias:
        result.append(registry[criteria["id"]](package))

    return result

def scorecard(packages: list[ContentPackage]) -> tuple:
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

