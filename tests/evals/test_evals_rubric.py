import pytest

from src.evals.rubric import load, select
from tests.helpers.content_package import baseline_package
from src.evals.rubric_eval import scorer, scorecard

# PARKED behind the single-shot pivot (plan Task 7): rubric selection + scoring
# tests built on the retired 3-shot schema (Device, baseline_package). Kept for
# a future vision judge; skipped to keep the suite green.
pytestmark = pytest.mark.skip(reason="rubric eval parked behind single-shot pivot (plan Task 7)")

def test_load():
    records = load()
    assert len(records) == 5


def test_select_encounter_returns_universals_only():
    # baseline_package() has device "encounter": the lone conditional criterion
    # (device_requires_event_beat, applies_when transformation/time_compression)
    # does NOT match, so only the 4 universal criteria survive.
    package = baseline_package()
    records = load()

    selected = select(package, records)

    assert len(selected) == 4
    ids = [record["id"] for record in selected]
    assert "device_requires_event_beat" not in ids


def test_select_change_device_includes_conditional():
    # When the package's device matches the conditional's applies_when (a
    # change-device: transformation / time_compression), the conditional
    # criterion is kept alongside the 4 universals.
    package = baseline_package()
    package.device = "transformation"
    records = load()

    selected = select(package, records)

    assert len(selected) == 5
    ids = [record["id"] for record in selected]
    assert "device_requires_event_beat" in ids


def test_scorer():
    result = scorer(baseline_package())
    assert len(result) == 4
    assert all(r.passed for r in result)

def test_scorecard():
    clean_a = baseline_package()
    clean_b = baseline_package()
    dirty = baseline_package()
    dirty.shots[2].start_keyframe = "the whale is as thick as"
    packages = [clean_a, clean_b, dirty]

    rates, failures = scorecard(packages)

    assert rates["no_scale_comparison"] == 2 / 3
    assert len(failures) == 1
    assert failures[0].criterion_id == "no_scale_comparison"