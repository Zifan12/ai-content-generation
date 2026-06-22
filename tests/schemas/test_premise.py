"""Tests for Premise and PremiseSet schemas (Task 2)."""

import pytest
from pydantic import ValidationError

from src.schemas.premise import Premise, PremiseSet


def _premise(n: int = 0) -> Premise:
    """One schema-valid Premise; n makes each string distinct in a slate."""
    return Premise(premise=f"Schema-test premise number {n} for validation.")


def _ten_premises() -> list[Premise]:
    return [_premise(i) for i in range(10)]


def test_premise_set_of_ten_validates():
    premise_set = PremiseSet(premises=_ten_premises())
    assert len(premise_set.premises) == 10


def test_premise_set_of_nine_raises():
    with pytest.raises(ValidationError):
        PremiseSet(premises=_ten_premises()[:9])


def test_premise_set_of_eleven_raises():
    with pytest.raises(ValidationError):
        PremiseSet(premises=_ten_premises() + [_premise(99)])


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
