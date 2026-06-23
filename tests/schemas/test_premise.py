"""Tests for Premise and PremiseSet schemas (Task 2)."""

import pytest
from pydantic import ValidationError

from src.schemas.premise import Premise, PremiseSet


def _premise(n: int = 0) -> Premise:
    """One schema-valid Premise; n makes each string distinct in a slate."""
    return Premise(premise=f"Schema-test premise number {n} for validation.")


def _n_premises(count: int) -> list[Premise]:
    return [_premise(i) for i in range(count)]


def test_premise_set_accepts_variable_n():
    for n in (1, 3, 10):
        premise_set = PremiseSet(premises=_n_premises(n))
        assert len(premise_set.premises) == n


def test_premise_set_empty_raises():
    with pytest.raises(ValidationError):
        PremiseSet(premises=[])


def test_premise_requires_only_premise():
    p = Premise(premise="A dog waits at the door as if someone is about to arrive.")
    assert p.why_arresting is None


def test_premise_why_arresting_optional():
    p = Premise(
        premise="Rain falls upward in a parking lot for three seconds.",
        why_arresting="Mundane setting plus impossible physics.",
    )
    assert p.why_arresting is not None


def test_premise_too_short_raises():
    with pytest.raises(ValidationError):
        Premise(premise="short")


def test_removed_winning_mechanics_rejected():
    with pytest.raises(ValidationError):
        Premise(
            premise="A glass cracks in a freezer without being touched.",
            winning_mechanics="loop dread",
        )


def test_removed_copies_nothing_rejected():
    with pytest.raises(ValidationError):
        Premise(
            premise="A glass cracks in a freezer without being touched.",
            copies_nothing="different subject from winners",
        )
