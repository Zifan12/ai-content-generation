"""
Tests for src/reference/ranking.py — fake verdicts only, no images, no LLM.

Covers the plan's test intent: angle coverage beats sharpness (a lone lower-
sharpness profile IS selected over a tenth frontal), every ineligibility class
is excluded, <k_min survivors return as-is, and ordering is deterministic.
"""

from src.reference.ranking import select_top
from src.reference.schemas import FrameScore, FrameVerdict


def _verdict(
    *,
    angle: str = "front",
    usable: bool = True,
    character_present: bool = True,
    text_or_watermark_overlap: bool = False,
    single_character: bool = True,
) -> FrameVerdict:
    return FrameVerdict(
        character_present=character_present,
        face_visibility="clear",
        text_or_watermark_overlap=text_or_watermark_overlap,
        angle=angle,  # type: ignore[arg-type]
        single_character=single_character,
        usable=usable,
        reason="test verdict",
    )


def _frame(path: str, sharpness: float, verdict: FrameVerdict | None) -> FrameScore:
    return FrameScore(path=path, sharpness=sharpness, verdict=verdict)


def test_lone_profile_selected_over_extra_frontals():
    # 10 sharp frontals + 1 much-blurrier profile: coverage round must pick
    # the profile even though 10 frontals outscore it on sharpness.
    frames = [
        _frame(f"front_{i}.png", 500.0 - i, _verdict(angle="front")) for i in range(10)
    ]
    frames.append(_frame("profile.png", 50.0, _verdict(angle="profile")))

    selected = select_top(frames, k_min=6, k_max=8)

    assert "profile.png" in [f.path for f in selected]
    assert len(selected) == 8


def test_core_angles_each_covered_before_depth():
    frames = [
        _frame("f1.png", 900.0, _verdict(angle="front")),
        _frame("f2.png", 800.0, _verdict(angle="front")),
        _frame("f3.png", 700.0, _verdict(angle="front")),
        _frame("tq.png", 100.0, _verdict(angle="three_quarter")),
        _frame("pr.png", 90.0, _verdict(angle="profile")),
    ]

    selected = select_top(frames, k_min=3, k_max=3)

    assert {f.path for f in selected} == {"f1.png", "tq.png", "pr.png"}


def test_back_and_unknown_fill_only_after_core():
    # One slot left after core coverage; a sharp back view competes with a
    # slightly-less-sharp second frontal — round 2 is sharpness-only, so the
    # back view wins the fill slot (back is fill-eligible, just not core).
    frames = [
        _frame("front1.png", 500.0, _verdict(angle="front")),
        _frame("tq.png", 400.0, _verdict(angle="three_quarter")),
        _frame("pr.png", 300.0, _verdict(angle="profile")),
        _frame("back.png", 450.0, _verdict(angle="back")),
        _frame("front2.png", 440.0, _verdict(angle="front")),
    ]

    selected = select_top(frames, k_min=4, k_max=4)

    paths = {f.path for f in selected}
    assert paths == {"front1.png", "tq.png", "pr.png", "back.png"}


def test_every_ineligibility_class_excluded():
    frames = [
        _frame("ok.png", 100.0, _verdict()),
        _frame("unjudged.png", 999.0, None),
        _frame("unusable.png", 999.0, _verdict(usable=False)),
        _frame("absent.png", 999.0, _verdict(character_present=False)),
        _frame("overlap.png", 999.0, _verdict(text_or_watermark_overlap=True)),
        _frame("multi.png", 999.0, _verdict(single_character=False)),
    ]

    selected = select_top(frames, k_min=1, k_max=8)

    assert [f.path for f in selected] == ["ok.png"]


def test_composite_usable_not_trusted_alone():
    # Judge said usable=True but its own component observation contradicts it
    # (text overlaps the character) — defensive D1 drops it.
    frames = [
        _frame(
            "contradiction.png",
            999.0,
            _verdict(usable=True, text_or_watermark_overlap=True),
        )
    ]

    assert select_top(frames, k_min=1, k_max=8) == []


def test_fewer_than_k_min_returned_as_is():
    frames = [
        _frame("a.png", 200.0, _verdict(angle="front")),
        _frame("b.png", 100.0, _verdict(angle="profile")),
    ]

    selected = select_top(frames, k_min=6, k_max=8)

    assert len(selected) == 2


def test_empty_input_returns_empty():
    assert select_top([], k_min=6, k_max=8) == []


def test_deterministic_order_sharpest_first_path_tiebreak():
    frames = [
        _frame("b.png", 100.0, _verdict(angle="front")),
        _frame("a.png", 100.0, _verdict(angle="profile")),
        _frame("c.png", 300.0, _verdict(angle="three_quarter")),
    ]

    selected = select_top(frames, k_min=3, k_max=3)
    selected_again = select_top(list(reversed(frames)), k_min=3, k_max=3)

    assert [f.path for f in selected] == ["c.png", "a.png", "b.png"]
    assert [f.path for f in selected_again] == [f.path for f in selected]


def test_k_max_caps_selection():
    frames = [
        _frame(f"f{i}.png", 100.0 + i, _verdict(angle="front")) for i in range(12)
    ]

    selected = select_top(frames, k_min=6, k_max=8)

    assert len(selected) == 8
