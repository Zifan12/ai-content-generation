"""Tests for the scene-lane render adapter (plan 2026-07-06 Task 4; legacy
still-first tests deleted Task 10).

Load-bearing: composition order + single constraint tail (anchors/style/refs
composed in CODE, byte-identical), positional ref bindings, and the crash-loud
guards (path convention, grounding, cast cap, char ceiling).
"""

import pytest

from src.generation.render_adapters.adapter import render_jobs
from src.generation.render_adapters.rules import RenderRules
from src.monitor.schemas import BeatRole
from src.schemas.generation import MotionTag, MultiShotPackage, ShotSpec

ANCHORS = "ANCHORS: Eve — short tousled dark-brown hair, pure-white armored bodysuit."
STYLE = "STYLE: cel-shaded TV anime, thick clean line art."


@pytest.fixture(scope="module")
def rules():
    return RenderRules()


# --- SCENE LANE (spec 2026-07-06 A3/D3) -------------------------------------------
# Every package yields ONE composed multi_shot job.


def _scene_shot(index: int, characters: list[str]) -> ShotSpec:
    return ShotSpec(
        beat_role=BeatRole.build,
        motion_tag=MotionTag.character_consistency,
        scene_line=f"LINE[{index}] Camera: slow push-in. Audio: rain.",
        duration_seconds=4,  # 3 shots x 4s = 12s, inside the 10-25 envelope
        narration_line=None,
        characters_in_frame=characters,
    )


def _scene_package(
    shots: list[ShotSpec] | None = None,
    refs: list[str] | None = None,
) -> MultiShotPackage:
    return MultiShotPackage(
        shots=shots
        or [
            _scene_shot(0, ["Eve"]),
            _scene_shot(1, ["Eve", "Adam"]),
            _scene_shot(2, ["Adam"]),
        ],
        style_anchor=STYLE,
        anchors_block=ANCHORS,
        hook_text=None,
        caption="c",
        hashtags=[],
        music_brief=None,
        reference_image_paths=refs
        if refs is not None
        else [
            # deliberately unsorted within Adam's folder — the adapter sorts
            "refs/adam/b_profile.png",
            "refs/adam/a_front.png",
            "refs/eve/front.png",
        ],
    )


def test_scene_package_yields_one_multi_shot_job(rules):
    jobs = render_jobs(_scene_package(), rules)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.kind == "multi_shot"
    assert job.model_cli_id == rules.scene_model()
    assert job.covers_shots == [0, 1, 2]
    assert job.duration == 15  # scene_lane.defaults.duration_seconds (bumped 10->15, 2026-07-10), under the cap
    assert job.aspect_ratio == "9:16"


def test_scene_refs_ordered_cast_first_appearance_then_filename(rules):
    job = render_jobs(_scene_package(), rules)[0]
    # Eve appears first (shot 0) so her refs upload first; Adam's sort by filename.
    assert job.reference_images == [
        "refs/eve/front.png",
        "refs/adam/a_front.png",
        "refs/adam/b_profile.png",
    ]
    # binding is TEXTUAL and positional — the prompt names each character's slots
    assert "Eve is the character shown in image1." in job.prompt
    assert "Adam is the character shown in image2, image3." in job.prompt


def test_scene_prompt_composition_order_and_single_tail(rules):
    job = render_jobs(_scene_package(), rules)[0]
    prompt = job.prompt
    # A3 order: style preamble -> identity (anchors + bindings) -> body -> tail
    positions = [
        prompt.index("Exactly matching the art style"),
        prompt.index(ANCHORS),
        prompt.index("LINE[0]"),
        prompt.index("No music."),
    ]
    assert positions == sorted(positions)
    # joined as one continuous scene: N-1 cuts, tail lines exactly once
    assert prompt.count("Then cut to:") == 2
    assert prompt.count("No music.") == 1
    assert prompt.count("Generate the video without subtitles.") == 1  # quality suffix
    # anchors travel via composition, not via the LLM's lines
    assert prompt.count(ANCHORS) == 1


def test_scene_char_cap_violation_raises(rules):
    shots = [
        _scene_shot(0, ["Eve", "Adam"]),
        _scene_shot(1, ["Bea", "Cal"]),
        _scene_shot(2, ["Eve"]),
    ]
    refs = [
        "refs/eve/f.png",
        "refs/adam/f.png",
        "refs/bea/f.png",
        "refs/cal/f.png",
    ]
    with pytest.raises(ValueError, match="max_characters_in_scene"):
        render_jobs(_scene_package(shots=shots, refs=refs), rules)


def test_scene_unattributed_ref_crashes_loud(rules):
    refs = [
        "refs/eve/front.png",
        "refs/adam/front.png",
        "render_taste_test/wistoria_refs/will_2_adult.png",  # flat legacy layout
    ]
    with pytest.raises(ValueError, match="matches no\s+cast member"):
        render_jobs(_scene_package(refs=refs), rules)


def test_scene_ungrounded_cast_member_crashes_loud(rules):
    refs = ["refs/eve/front.png"]  # Adam has no sheet
    with pytest.raises(ValueError, match="no reference images"):
        render_jobs(_scene_package(refs=refs), rules)


# --- LOCATION GROUNDING (spec 2026-07-10, decisions locked 2026-07-11) ------------
# A location is NOT a cast member: its refs upload AFTER character refs, get their
# own positional "(imageN)" setting binding, and bypass the cast crash-guard.


def _single_char_package(refs: list[str]) -> MultiShotPackage:
    """A 3-shot package with Eve as the only cast member, for predictable slots."""
    return _scene_package(
        shots=[_scene_shot(0, ["Eve"]), _scene_shot(1, ["Eve"]), _scene_shot(2, ["Eve"])],
        refs=refs,
    )


def test_location_ref_uploads_after_character_refs(rules):
    pkg = _single_char_package(["refs/eve/front.png"])
    pkg.world_anchor = "A grand ice-tower chamber, pale marble floor."
    pkg.location_reference_paths = ["refs/_location/elfie_bedroom/room.jpg"]
    job = render_jobs(pkg, rules)[0]
    # character ref first, location ref LAST — order IS the CLI upload order
    assert job.reference_images == [
        "refs/eve/front.png",
        "refs/_location/elfie_bedroom/room.jpg",
    ]
    # world_anchor appended verbatim + positional setting binding at slot 2
    assert "A grand ice-tower chamber" in job.prompt
    assert "The setting is shown in image2." in job.prompt


def test_location_setting_block_sits_after_identity_before_body(rules):
    pkg = _single_char_package(["refs/eve/front.png"])
    pkg.world_anchor = "A grand ice-tower chamber."
    pkg.location_reference_paths = ["refs/_location/elfie_bedroom/room.jpg"]
    prompt = render_jobs(pkg, rules)[0].prompt
    positions = [
        prompt.index(ANCHORS),                       # identity
        prompt.index("A grand ice-tower chamber."),  # setting
        prompt.index("LINE[0]"),                     # body
    ]
    assert positions == sorted(positions)


def test_no_location_prompt_and_refs_unchanged(rules):
    # An ungrounded package composes exactly as before this feature.
    job = render_jobs(_scene_package(), rules)[0]
    assert "The setting is shown in" not in job.prompt
    assert all("_location" not in ref for ref in job.reference_images)


def test_location_ref_does_not_trip_cast_crash_guard(rules):
    # refs/_location/... has no matching cast slug — it must NOT crash the way an
    # unattributed CHARACTER ref does (that path is the separate lane).
    pkg = _single_char_package(["refs/eve/front.png"])
    pkg.location_reference_paths = ["refs/_location/elfie_bedroom/room.jpg"]
    job = render_jobs(pkg, rules)[0]  # no raise
    assert "refs/_location/elfie_bedroom/room.jpg" in job.reference_images


def test_location_ref_counts_against_image_cap(rules):
    cap = rules.model(rules.scene_model())["limits"]["max_image_references"]
    char_refs = [f"refs/eve/{i:02d}.png" for i in range(cap)]  # fills the cap
    pkg = _single_char_package(char_refs)
    pkg.location_reference_paths = ["refs/_location/elfie_bedroom/room.jpg"]  # cap + 1
    with pytest.raises(ValueError, match="max_image_references"):
        render_jobs(pkg, rules)


def test_scene_prompt_over_char_ceiling_raises(rules):
    long_shots = [
        ShotSpec(
            beat_role=BeatRole.build,
            motion_tag=MotionTag.character_consistency,
            scene_line="x" * 1200 + f" LINE[{i}]. Audio: rain.",
            duration_seconds=4,
            narration_line=None,
            characters_in_frame=["Eve"],
        )
        for i in range(3)
    ]
    refs = ["refs/eve/front.png"]
    with pytest.raises(ValueError, match="max_prompt_chars"):
        render_jobs(_scene_package(shots=long_shots, refs=refs), rules)
