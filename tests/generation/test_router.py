"""Tests for the shot router (plan 2026-07-04 Task 3).

Two functions under test:
  - route_shots: every shot's model is the FIRST-ranked entry for its motion_tag in
    config/render_rules.yaml — the audit-issue-10 fix (routing table goes live).
  - consistency_groups: contiguous shots routed to the same multi-shot-capable model
    with IDENTICAL character sets merge into one group, bounded by the model's own
    yaml caps (ratings.max_shots / ratings.max_seconds). Everything else is a
    singleton group.

Grouping rules v1 (decisions flagged for user ratification in the plan):
  - IDENTICAL character sets, not pairwise overlap: a group renders as ONE
    generation seeded by ONE grounded still — the first shot's frame. A character
    who first appears mid-group would not exist in that seed still and would render
    UNGROUNDED (the BUG-002 failure class). Identical sets guarantee every group
    member's cast is exactly the seed still's cast.
  - Hard yaml caps only; the ~10s soft preference is writer-side duration guidance
    (call-1 prompt), NOT a grouping split — splitting at 10s can strand a 1-shot
    tail, and a singleton group re-introduces the independent-still drift the
    grouping exists to avoid.
"""

import pytest

from src.generation.render_adapters.router import (
    RoutingDecision,
    consistency_groups,
    route_shots,
)
from src.generation.render_adapters.rules import RenderRules
from src.monitor.schemas import BeatRole
from src.schemas.generation import MotionTag, ShotDraft


def _draft(
    tag: MotionTag,
    characters: list[str] | None = None,
    duration: int = 4,
) -> ShotDraft:
    return ShotDraft(
        beat_role=BeatRole.build,
        motion_tag=tag,
        still_prompt="Wide shot, rain-slick alley, subject centered.",
        motion_intent="Slow push-in, subject turns on the final second, rain falling.",
        duration_seconds=duration,
        narration_line=None,
        characters_in_frame=characters if characters is not None else ["Eve"],
    )


@pytest.fixture(scope="module")
def rules() -> RenderRules:
    return RenderRules()


# --- route_shots ---------------------------------------------------------------


def test_every_tag_routes_to_first_ranked_yaml_model(rules):
    drafts = [_draft(tag) for tag in MotionTag]
    decisions = route_shots(drafts, rules)
    assert len(decisions) == len(drafts)
    for i, (tag, decision) in enumerate(zip(MotionTag, decisions)):
        assert decision.shot_index == i
        assert decision.motion_tag == tag
        assert decision.model_cli_id == rules.route(tag.value)[0]


def test_routing_decisions_carry_a_reason(rules):
    decisions = route_shots([_draft(MotionTag.fluid_motion)], rules)
    assert decisions[0].model_cli_id == "veo3_1"  # hailuo pulled (BUG-011)
    assert decisions[0].reason  # non-empty, self-documenting (OpenMontage pattern)


def test_character_consistency_routes_kling_first(rules):
    decisions = route_shots([_draft(MotionTag.character_consistency)], rules)
    assert decisions[0].model_cli_id == "kling3_0"


def test_spectacle_routes_seedance_first(rules):
    decisions = route_shots([_draft(MotionTag.spectacle)], rules)
    assert decisions[0].model_cli_id == "seedance_2_0"


# --- consistency_groups ----------------------------------------------------------


def _grouped(drafts: list[ShotDraft], rules: RenderRules) -> list[list[int]]:
    return consistency_groups(drafts, route_shots(drafts, rules), rules)


def test_three_contiguous_kling_shots_same_cast_one_group(rules):
    # NOTE (discovered red-green 2026-07-05): a 4-shot kling group is
    # UNCONSTRUCTIBLE — 4 shots x 4s schema floor = 16s > kling max_seconds 15.
    # Real kling groups are 2-3 shots; max_shots(6) is unreachable at our floor.
    drafts = [_draft(MotionTag.character_consistency) for _ in range(3)]
    assert _grouped(drafts, rules) == [[0, 1, 2]]


def test_four_kling_shots_split_by_duration_floor(rules):
    drafts = [_draft(MotionTag.character_consistency) for _ in range(4)]  # 4 x 4s
    assert _grouped(drafts, rules) == [[0, 1, 2], [3]]


def test_breakout_shot_is_never_bridged(rules):
    drafts = [
        _draft(MotionTag.character_consistency),
        _draft(MotionTag.fluid_motion),
        _draft(MotionTag.character_consistency),
    ]
    assert _grouped(drafts, rules) == [[0], [1], [2]]


def test_cast_change_splits_the_group(rules):
    drafts = [
        _draft(MotionTag.character_consistency, characters=["Eve"]),
        _draft(MotionTag.character_consistency, characters=["Eve"]),
        _draft(MotionTag.character_consistency, characters=["Eve", "Adam"]),
    ]
    # Adam is absent from the group's seed still (shot 0's frame) — he would render
    # ungrounded if bridged in. Identical-set rule splits instead.
    assert _grouped(drafts, rules) == [[0, 1], [2]]


def test_cast_order_does_not_split(rules):
    drafts = [
        _draft(MotionTag.character_consistency, characters=["Eve", "Adam"]),
        _draft(MotionTag.character_consistency, characters=["Adam", "Eve"]),
        _draft(MotionTag.character_consistency, characters=["Eve", "Adam"]),
    ]
    assert _grouped(drafts, rules) == [[0, 1, 2]]


def test_duration_cap_splits_at_yaml_max_seconds(rules):
    # 4 kling shots x 5s = 20s > kling max_seconds 15 -> split [0,1,2] (15s) + [3].
    drafts = [
        _draft(MotionTag.character_consistency, duration=5) for _ in range(4)
    ]
    assert _grouped(drafts, rules) == [[0, 1, 2], [3]]


def test_non_multishot_models_always_singletons(rules):
    # fluid_motion routes to veo3_1 (hailuo pulled, BUG-011), no ratings.max_shots entry —
    # contiguous same-cast hailuo shots must NOT merge.
    drafts = [_draft(MotionTag.fluid_motion) for _ in range(3)]
    assert _grouped(drafts, rules) == [[0], [1], [2]]


def test_empty_casts_merge_together(rules):
    drafts = [
        _draft(MotionTag.character_consistency, characters=[]),
        _draft(MotionTag.character_consistency, characters=[]),
        _draft(MotionTag.character_consistency, characters=["Eve"]),
    ]
    assert _grouped(drafts, rules) == [[0, 1], [2]]


def test_groups_cover_every_shot_exactly_once(rules):
    drafts = [
        _draft(MotionTag.character_consistency),
        _draft(MotionTag.spectacle),
        _draft(MotionTag.character_consistency),
        _draft(MotionTag.character_consistency),
        _draft(MotionTag.impossible_physics),
    ]
    groups = _grouped(drafts, rules)
    flattened = [i for group in groups for i in group]
    assert sorted(flattened) == list(range(len(drafts)))
    assert flattened == sorted(flattened)  # shot order preserved across groups


def test_routing_decision_is_a_typed_record(rules):
    decision = route_shots([_draft(MotionTag.character_consistency)], rules)[0]
    assert isinstance(decision, RoutingDecision)
