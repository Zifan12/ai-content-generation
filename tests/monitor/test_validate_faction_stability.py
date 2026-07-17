"""Tests for the faction-map shuffle-stability harness (Exilus ticket 08).

Per the ticket's Test notes: only the harness's OWN control flow (variant
generation, per-variant/per-thread bookkeeping, report assembly) is
test-assertable -- the live paid faction-reader call is manual, out of the
automated suite (same seam pattern as every other monitor-agent test: a fake
stands in for the real LLM-backed component). Whether the faction-reader's
camps are actually "the same" across variants is explicitly NOT
test-assertable (human judgment only).
"""

from collections import Counter

from src.monitor.schemas import Camp, EvidenceQuote, FactionMap
from scripts.validate_faction_stability import (
    format_report,
    make_variants,
    run_stability_validation,
)


def _camp(name: str, weight: float = 1.0) -> Camp:
    return Camp(
        name=name,
        feeling="hopeful",
        surface_want=f"{name} wants X",
        deeper_desire=f"{name} secretly wants Y",
        evidence_quotes=[EvidenceQuote(quote="I wish they did X", upvotes=42)],
        weight=weight,
    )


def _map(*camp_names: str, thin_data: bool = False) -> FactionMap:
    n = len(camp_names)
    return FactionMap(
        camps=[_camp(name, weight=1.0 / n) for name in camp_names], thin_data=thin_data
    )


class FakeFactionReader:
    """Returns a queued FactionMap (or raises a queued exception) per
    ``read()`` call, keyed by topic -- each thread gets its own queue so
    per-thread results are asserted independently, and topic/reddit_text
    arguments are recorded for call-shape assertions."""

    def __init__(self, results_by_topic: dict[str, list]) -> None:
        self._queues = {k: list(v) for k, v in results_by_topic.items()}
        self.calls: list[tuple[str, str]] = []

    def read(self, topic: str, reddit_text: str) -> FactionMap:
        self.calls.append((topic, reddit_text))
        result = self._queues[topic].pop(0)
        if isinstance(result, Exception):
            raise result
        return result


# ---------------------------------------------------------------------------
# AC1/AC4: variant generation is pure, no comment ever introduced that
# wasn't in the original floor-filtered set.
# ---------------------------------------------------------------------------


def test_make_variants_never_introduces_a_comment_outside_the_original_set():
    comments = [f"[COMMENT | {i} upvotes] body {i}" for i in range(20)]

    variants = make_variants(comments, n_variants=5, drop_fraction=0.3, seed=1)

    assert len(variants) == 5
    for variant in variants:
        # Every comment in the variant came from the original set, and
        # never more than once (a strict subset, not a resample-with-replacement).
        counts = Counter(variant)
        for comment, count in counts.items():
            assert comment in comments
            assert count == 1


def test_make_variants_pure_shuffle_keeps_every_comment():
    comments = [f"c{i}" for i in range(10)]

    variants = make_variants(comments, n_variants=3, drop_fraction=0.0, seed=42)

    for variant in variants:
        assert sorted(variant) == sorted(comments)


def test_make_variants_subsample_drops_the_requested_fraction():
    comments = [f"c{i}" for i in range(10)]

    variants = make_variants(comments, n_variants=4, drop_fraction=0.5, seed=7)

    for variant in variants:
        assert len(variant) == 5


def test_make_variants_is_pure_no_network_no_llm(monkeypatch):
    """AC4: variant generation never touches an LLM or network resource --
    exercisable with only a fixed fake comment list. There is nothing in
    scripts.validate_faction_stability's ``make_variants`` importable that
    could reach the network; this test just confirms it runs to completion
    against a fixed list with no injected fake needed at all."""
    comments = ["a", "b", "c"]
    variants = make_variants(comments, n_variants=2, seed=None)
    assert len(variants) == 2


# ---------------------------------------------------------------------------
# Thread isolation + no camp-count normalization (PRD test notes)
# ---------------------------------------------------------------------------


def test_threads_are_isolated_from_each_other():
    reader = FakeFactionReader(
        {
            "thread-a": [_map("camp-a1"), _map("camp-a1"), _map("camp-a1")],
            "thread-b": [_map("camp-b1", "camp-b2"), _map("camp-b1", "camp-b2"), _map("camp-b1", "camp-b2")],
        }
    )
    threads = {
        "thread-a": [f"a-comment-{i}" for i in range(10)],
        "thread-b": [f"b-comment-{i}" for i in range(10)],
    }

    results = run_stability_validation(reader, threads, n_variants=3, seed=1)

    assert set(results.keys()) == {"thread-a", "thread-b"}
    assert all(fmap.camps[0].name == "camp-a1" for fmap in results["thread-a"])
    assert all(
        {c.name for c in fmap.camps} == {"camp-b1", "camp-b2"} for fmap in results["thread-b"]
    )
    # Every recorded call's reddit_text only ever contains that thread's own comments.
    for topic, reddit_text in reader.calls:
        if topic == "thread-a":
            assert "b-comment" not in reddit_text
        else:
            assert "a-comment" not in reddit_text


def test_no_camp_count_normalization_single_and_max_camps_pass_through():
    """A fake response with 1 camp and a separate fake response at the
    FactionMap schema's own max (5 -- ticket 05's post-emergence cap) both
    pass through into the results unmodified (single-camp-legal + no
    ADDITIONAL harness-side cap on top of what the reader already applied,
    User Stories 12-13)."""
    reader = FakeFactionReader(
        {
            "solo-thread": [_map("only-camp")],
            "split-thread": [_map("c1", "c2", "c3", "c4", "c5")],
        }
    )
    threads = {"solo-thread": ["x"], "split-thread": ["y"]}

    results = run_stability_validation(reader, threads, n_variants=1, seed=1)

    assert len(results["solo-thread"][0].camps) == 1
    assert len(results["split-thread"][0].camps) == 5  # harness applies no cap of its own


# ---------------------------------------------------------------------------
# Per-variant isolation: one bad variant doesn't kill the run.
# ---------------------------------------------------------------------------


def test_one_failing_variant_is_recorded_as_none_others_still_run():
    reader = FakeFactionReader(
        {"flaky-thread": [_map("ok1"), RuntimeError("transient failure"), _map("ok2")]}
    )
    threads = {"flaky-thread": [f"c{i}" for i in range(10)]}

    results = run_stability_validation(reader, threads, n_variants=3, seed=1)

    maps = results["flaky-thread"]
    assert len(maps) == 3
    assert maps[0] is not None and maps[0].camps[0].name == "ok1"
    assert maps[1] is None
    assert maps[2] is not None and maps[2].camps[0].name == "ok2"


# ---------------------------------------------------------------------------
# Report: no computed verdict, camp/thread content shown as-is.
# ---------------------------------------------------------------------------


def test_format_report_lists_all_camps_with_no_computed_verdict():
    results = {
        "thread-1": [_map("camp-x"), _map("camp-x", "camp-y", thin_data=True)],
    }

    report = format_report(results)

    assert "thread-1" in report
    assert "camp-x" in report
    assert "camp-y" in report
    assert "THIN DATA" in report
    for banned in ("PASS", "FAIL", "STABLE", "UNSTABLE", "MATCH"):
        assert banned not in report.upper().replace("THIN DATA", "")


def test_format_report_marks_failed_variants():
    results = {"thread-1": [None, _map("camp-x")]}

    report = format_report(results)

    assert "FAILED" in report
    assert "camp-x" in report
