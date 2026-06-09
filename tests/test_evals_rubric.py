from src.evals.rubric import load, select
from tests.test_rubric_checks import baseline_package
from src.evals.rubric_eval import scorer, scorecard

def test_load():
    records = load()
    assert len(records) == 6


def test_select_sustained_mood_returns_universals_only():
    # baseline_package() is sustained_mood: the lone conditional criterion
    # (escalating_wrongness_has_event_beat) does NOT match, so only the 5
    # universal criteria survive.
    package = baseline_package()
    records = load()

    selected = select(package, records)

    assert len(selected) == 5
    ids = [record["id"] for record in selected]
    assert "escalating_wrongness_has_event_beat" not in ids


def test_select_escalating_wrongness_includes_conditional():
    # When the package's organizing_principle matches the conditional's
    # applies_when, the conditional criterion is kept alongside the 5 universals.
    package = baseline_package()
    package.organizing_principle = "escalating_wrongness"
    records = load()

    selected = select(package, records)

    assert len(selected) == 6
    ids = [record["id"] for record in selected]
    assert "escalating_wrongness_has_event_beat" in ids


def test_scorer():
    result = scorer(baseline_package())
    assert len(result) == 5
    assert all(r.passed for r in result)

def test_scorecard():
    clean_a = baseline_package()
    clean_b = baseline_package()
    dirty = baseline_package()
    dirty.shots[2].start_keyframe = "the whale is as thick as"
    packages = [clean_a, clean_b, dirty]

    rates, failures = scorecard(packages)

    assert rates["no_scale_comparison"] == 2 / 3
    assert rates["mood_anchor_identical"] == 1
    assert len(failures) == 1
    assert failures[0].criterion_id == "no_scale_comparison"