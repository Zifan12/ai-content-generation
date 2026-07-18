"""Tests for POV script structural validation + bounded repair (ticket 04).

Two seams, mirroring test_compiler.py's own split:

- Seam 2 (pure function): ``check_structure`` — script + rules in, a
  violation list out, no LLM, no I/O. One test per violation class plus a
  fully-valid script.
- Seam 1 (orchestration with a fake seat): ``develop_valid_script`` — proves
  the bounded-repair contract itself: valid scripts pass through with zero
  repair calls; a violating first draft triggers exactly one repair call and
  the repaired output is accepted when it is clean; a violation surviving
  that one repair raises POVStructuralViolationError naming the violation
  (never a silent pass-through).

Beat-budget assertions read ``RenderRules().pov_grammar()["beat_budget"]``
live rather than hardcoding 4-6/5-8 in this file, so a future config edit
can't silently drift out of sync with what these tests actually prove
(same convention as test_compiler.py).
"""

import pytest

from src.generation.pov.craft_enforcement import (
    POVStructuralViolationError,
    check_structure,
    develop_valid_script,
)
from src.generation.pov.schemas import POVBeat, POVPitch, POVScript
from src.generation.render_adapters.rules import RenderRules

SAMPLE_PITCH = POVPitch(
    who="a cave explorer",
    where="a crystal cavern deep underground",
    what_happens="the explorer finds a glowing shard and lifts it toward their eyes",
    turn="the shard's glow reveals the cavern is not empty after all",
    money_shot="the raised shard lights the cavern and hundreds of eyes open at once",
)


@pytest.fixture(scope="module")
def rules() -> RenderRules:
    return RenderRules()


def _valid_script(duration_seconds: int = 10) -> POVScript:
    """A script with exactly the minimum beat count for its duration's budget,
    no beat over 2 actions, and no dialogue on the last beat — structurally clean."""
    beat_count = 4 if duration_seconds == 10 else 5
    beats = [
        POVBeat(actions=[f"the hand reaches for object {i}", f"the hand grips object {i}"])
        for i in range(beat_count)
    ]
    return POVScript(
        scene_setting="a damp crystal cavern",
        protagonist_role="explorer",
        protagonist_detail="with a headlamp, gloved hands occasionally visible",
        duration_seconds=duration_seconds,
        camera_register="calm",
        beats=beats,
        world_prose="Foreground rubble glistens, midground crystals pulse blue light.",
    )


# --- Seam 2: check_structure (pure function) --------------------------------


@pytest.mark.parametrize("duration_seconds", [10, 15])
def test_valid_script_has_no_violations(rules: RenderRules, duration_seconds: int) -> None:
    assert check_structure(_valid_script(duration_seconds), rules) == []


@pytest.mark.parametrize("bad_duration", [8, 12, 20, 0])
def test_duration_outside_10_or_15_is_a_violation(rules: RenderRules, bad_duration: int) -> None:
    script = _valid_script(10).model_copy(update={"duration_seconds": bad_duration})
    violations = check_structure(script, rules)
    assert any(str(bad_duration) in v for v in violations)


def test_beat_count_below_the_10s_budget_is_a_violation(rules: RenderRules) -> None:
    budget = rules.pov_grammar()["beat_budget"]["at_10s"]
    script = _valid_script(10)
    too_few = script.beats[: budget["min"] - 1]
    script = script.model_copy(update={"beats": too_few})

    violations = check_structure(script, rules)
    assert any("beat count" in v for v in violations)


def test_beat_count_above_the_15s_budget_is_a_violation(rules: RenderRules) -> None:
    budget = rules.pov_grammar()["beat_budget"]["at_15s"]
    script = _valid_script(15)
    too_many = list(script.beats) + [
        POVBeat(actions=["an extra action"]) for _ in range(budget["max"] + 1 - len(script.beats))
    ]
    script = script.model_copy(update={"beats": too_many})

    violations = check_structure(script, rules)
    assert any("beat count" in v for v in violations)


def test_invalid_duration_does_not_also_report_a_beat_budget_violation(
    rules: RenderRules,
) -> None:
    """An invalid duration has no budget to check the beat count against —
    check_structure should report the duration problem alone, not a
    confusing second violation about a budget that does not apply."""
    script = _valid_script(10).model_copy(update={"duration_seconds": 12})
    violations = check_structure(script, rules)
    assert len(violations) == 1
    assert "duration_seconds" in violations[0]


def test_beat_with_more_than_two_actions_is_a_violation(rules: RenderRules) -> None:
    script = _valid_script(10)
    beats = list(script.beats)
    beats[1] = POVBeat(actions=["action one", "action two", "action three"])
    script = script.model_copy(update={"beats": beats})

    violations = check_structure(script, rules)
    assert any("beat 1" in v and "actions" in v for v in violations)


def test_multiple_overloaded_beats_each_get_their_own_violation(rules: RenderRules) -> None:
    script = _valid_script(10)
    beats = list(script.beats)
    beats[0] = POVBeat(actions=["a", "b", "c"])
    beats[2] = POVBeat(actions=["d", "e", "f", "g"])
    script = script.model_copy(update={"beats": beats})

    violations = check_structure(script, rules)
    action_violations = [v for v in violations if "actions" in v]
    assert len(action_violations) == 2
    assert any("beat 0" in v for v in action_violations)
    assert any("beat 2" in v for v in action_violations)


def test_dialogue_on_the_final_beat_is_a_violation(rules: RenderRules) -> None:
    script = _valid_script(10)
    beats = list(script.beats)
    beats[-1] = POVBeat(
        actions=beats[-1].actions, dialogue_line="careful now", speaker="the explorer"
    )
    script = script.model_copy(update={"beats": beats})

    violations = check_structure(script, rules)
    assert any("final beat" in v or "last beat" in v for v in violations)


def test_dialogue_on_a_non_final_beat_is_not_a_violation(rules: RenderRules) -> None:
    script = _valid_script(10)
    beats = list(script.beats)
    beats[0] = POVBeat(
        actions=beats[0].actions, dialogue_line="careful now", speaker="the explorer"
    )
    script = script.model_copy(update={"beats": beats})

    assert check_structure(script, rules) == []


def test_a_script_can_carry_multiple_violations_at_once(rules: RenderRules) -> None:
    script = _valid_script(10).model_copy(update={"duration_seconds": 11})
    beats = list(script.beats)
    beats[0] = POVBeat(actions=["a", "b", "c"])
    beats[-1] = POVBeat(actions=["x"], dialogue_line="bye", speaker="the explorer")
    script = script.model_copy(update={"beats": beats})

    violations = check_structure(script, rules)
    assert len(violations) >= 3  # duration, action count, final-beat dialogue


# --- Seam 1: develop_valid_script (bounded-repair orchestration) ------------


class FakeScriptWriter:
    """Records develop/repair calls; returns configured scripts for each."""

    def __init__(self, first: POVScript, repaired: POVScript | None = None) -> None:
        self._first = first
        self._repaired = repaired
        self.develop_calls: list[POVPitch] = []
        self.repair_calls: list[tuple[POVPitch, POVScript, list[str]]] = []

    def develop(self, pitch: POVPitch) -> POVScript:
        self.develop_calls.append(pitch)
        return self._first

    def repair(
        self, pitch: POVPitch, failed_script: POVScript, violations: list[str]
    ) -> POVScript:
        self.repair_calls.append((pitch, failed_script, violations))
        assert self._repaired is not None, "test did not configure a repaired script"
        return self._repaired


def test_valid_script_passes_through_with_zero_repair_calls(rules: RenderRules) -> None:
    writer = FakeScriptWriter(_valid_script(10))

    result = develop_valid_script(writer, SAMPLE_PITCH, rules)

    assert result is writer._first
    assert len(writer.develop_calls) == 1
    assert writer.repair_calls == []


@pytest.mark.parametrize(
    "make_violating",
    [
        lambda s: s.model_copy(update={"duration_seconds": 11}),
        lambda s: s.model_copy(update={"beats": s.beats[:1]}),
        lambda s: s.model_copy(
            update={"beats": [POVBeat(actions=["a", "b", "c"]), *s.beats[1:]]}
        ),
        lambda s: s.model_copy(
            update={
                "beats": [
                    *s.beats[:-1],
                    POVBeat(actions=["x"], dialogue_line="bye", speaker="e"),
                ]
            }
        ),
    ],
    ids=["bad_duration", "beat_count_too_low", "too_many_actions", "final_beat_dialogue"],
)
def test_each_violation_class_triggers_exactly_one_repair_and_is_accepted(
    rules: RenderRules, make_violating
) -> None:
    violating = make_violating(_valid_script(10))
    fixed = _valid_script(10)
    writer = FakeScriptWriter(violating, repaired=fixed)

    result = develop_valid_script(writer, SAMPLE_PITCH, rules)

    assert result is fixed
    assert len(writer.develop_calls) == 1
    assert len(writer.repair_calls) == 1
    repair_pitch, repair_failed_script, repair_violations = writer.repair_calls[0]
    assert repair_pitch is SAMPLE_PITCH
    assert repair_failed_script is violating
    assert repair_violations == check_structure(violating, rules)
    assert repair_violations != []


def test_pitch_is_never_regenerated_only_the_script_is_repaired(rules: RenderRules) -> None:
    """PRD: 'Repair prompts re-target the script seat only; the pitch is
    never regenerated.' develop is called with the SAME pitch object both
    times a script is requested (there is no second pitch call at all —
    repair takes the pitch as an argument, never re-derives it)."""
    violating = _valid_script(10).model_copy(update={"duration_seconds": 9})
    fixed = _valid_script(10)
    writer = FakeScriptWriter(violating, repaired=fixed)

    develop_valid_script(writer, SAMPLE_PITCH, rules)

    assert writer.develop_calls == [SAMPLE_PITCH]
    assert writer.repair_calls[0][0] is SAMPLE_PITCH


def test_unrepairable_violation_raises_with_the_violation_named(rules: RenderRules) -> None:
    violating = _valid_script(10).model_copy(update={"duration_seconds": 9})
    # Repair "fixes" nothing — still an invalid duration.
    still_violating = violating
    writer = FakeScriptWriter(violating, repaired=still_violating)

    with pytest.raises(POVStructuralViolationError) as exc_info:
        develop_valid_script(writer, SAMPLE_PITCH, rules)

    assert len(writer.repair_calls) == 1  # bounded — exactly one, never a retry loop
    assert "duration_seconds" in str(exc_info.value)


def test_unrepairable_violation_lists_every_surviving_violation(rules: RenderRules) -> None:
    violating = _valid_script(10)
    beats = list(violating.beats)
    beats[0] = POVBeat(actions=["a", "b", "c"])
    violating = violating.model_copy(update={"beats": beats})
    writer = FakeScriptWriter(violating, repaired=violating)  # repair is a no-op

    with pytest.raises(POVStructuralViolationError) as exc_info:
        develop_valid_script(writer, SAMPLE_PITCH, rules)

    assert "beat 0" in str(exc_info.value)
    assert "actions" in str(exc_info.value)


def test_word_budget_breach_is_a_repairable_violation(rules: RenderRules) -> None:
    """First live run (2026-07-17): a 318-word body died at the compiler's
    hard backstop with no repair chance. The budget is now part of the
    repairable structural set — an over-budget script must produce a named
    violation here, not only a compiler error."""
    script = _valid_script(10)
    script = script.model_copy(
        update={"world_prose": " ".join(["word"] * 400)}
    )
    violations = check_structure(script, rules)
    assert any("word budget" in v for v in violations)
