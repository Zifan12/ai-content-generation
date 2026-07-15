"""Tests for the scene-lane render adapter (plan 2026-07-06 Task 4; legacy
still-first tests deleted Task 10).

Load-bearing: composition order + single constraint tail (anchors/style/refs
composed in CODE, byte-identical), positional ref bindings, and the crash-loud
guards (path convention, grounding, cast cap, char ceiling).
"""

import pytest

from src.generation.render_adapters.adapter import _shot_jobs, render_jobs
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


# --- PER-SCENE SPLICE LANE (_shot_jobs, Way 2, 2026-07-14 grill Q1-Q4) ------------
# One standalone generation per shot, each scoped to that shot's OWN cast.
# The default _scene_package() is the load-bearing fixture here: shot 0 is Eve-only
# while the package also carries Adam's refs — the exact case that must NOT trip the
# unattributed-ref guard once the package is sliced down to one shot.


_FOUR_CAST_REFS = [
    "refs/eve/f.png",
    "refs/adam/f.png",
    "refs/bea/f.png",
    "refs/cal/f.png",
]


def _four_cast_split_across_shots_package() -> MultiShotPackage:
    """4 characters package-wide, never more than 2 in any one shot (grill Q4).

    Three shots because MultiShotPackage enforces min_length=3 (and a 10-25s
    total) — the package the writer would really hand us always has 3-5.
    """
    return _scene_package(
        shots=[
            _scene_shot(0, ["Eve", "Adam"]),
            _scene_shot(1, ["Bea", "Cal"]),
            _scene_shot(2, ["Eve"]),
        ],
        refs=_FOUR_CAST_REFS,
    )


def _over_cap_single_shot_package() -> MultiShotPackage:
    """Shot 0 alone holds 4 characters — over the cap even after per-shot scoping."""
    return _scene_package(
        shots=[
            _scene_shot(0, ["Eve", "Adam", "Bea", "Cal"]),
            _scene_shot(1, ["Eve"]),
            _scene_shot(2, ["Adam"]),
        ],
        refs=_FOUR_CAST_REFS,
    )


def test_shot_jobs_returns_one_job_per_shot(rules):
    package = _scene_package()
    jobs = _shot_jobs(package, rules)
    assert len(jobs) == len(package.shots)
    for i, job in enumerate(jobs):
        assert job.kind == "scene_shot"
        assert job.covers_shots == [i]
        assert job.shot_index == i
        assert job.model_cli_id == rules.scene_model()


def test_shot_jobs_scopes_refs_to_that_shots_cast_only(rules):
    # default package: shot 0 = Eve, shot 1 = Eve + Adam, shot 2 = Adam (grill Q3)
    jobs = _shot_jobs(_scene_package(), rules)
    assert jobs[0].reference_images == ["refs/eve/front.png"]
    assert jobs[1].reference_images == [
        "refs/eve/front.png",
        "refs/adam/a_front.png",
        "refs/adam/b_profile.png",
    ]
    assert jobs[2].reference_images == ["refs/adam/a_front.png", "refs/adam/b_profile.png"]


def test_shot_jobs_rebinds_image_slots_per_shot(rules):
    """Slots renumber per generation: Adam is image2-3 in the 2-hander but
    image1-2 in his solo shot — each shot is its own independent upload."""
    jobs = _shot_jobs(_scene_package(), rules)
    assert "Adam is the character shown in image2, image3." in jobs[1].prompt
    assert "Adam is the character shown in image1, image2." in jobs[2].prompt
    # a shot never names a character who is not in it
    assert "Adam" not in jobs[0].prompt.split("LINE[0]")[0]


def test_shot_jobs_body_has_no_cut_transition(rules):
    """Each generation covers ONE shot, so nothing to cut to — the 'Then cut to:'
    chaining belongs to the single_gen lane alone."""
    for job in _shot_jobs(_scene_package(), rules):
        assert "Then cut to:" not in job.prompt


def test_shot_jobs_uses_splice_defaults_duration(rules):
    """Duration comes from scene_lane.splice_defaults, NOT the package's
    ShotSpec.duration_seconds narration estimate (grill Q2)."""
    jobs = _shot_jobs(_scene_package(), rules)
    expected = int(rules.data["scene_lane"]["splice_defaults"]["duration_seconds"])
    assert expected != _scene_package().shots[0].duration_seconds  # guards the point
    assert all(job.duration == expected for job in jobs)


def test_shot_jobs_caps_cast_per_shot_not_whole_package(rules):
    """4 characters package-wide but <=2 per shot -> splice passes where the
    single_gen lane rejects the very same package (grill Q4)."""
    package = _four_cast_split_across_shots_package()
    jobs = _shot_jobs(package, rules)  # must NOT raise
    assert len(jobs) == 3
    with pytest.raises(ValueError, match="max_characters_in_scene"):
        render_jobs(package, rules)  # single_gen (default mode) still rejects it


def test_shot_jobs_rejects_over_cap_single_shot(rules):
    """The cap did not disappear, it moved to per-shot — and the error names
    which shot blew it."""
    with pytest.raises(ValueError, match="shot 0:.*max_characters_in_scene"):
        _shot_jobs(_over_cap_single_shot_package(), rules)


def test_shot_jobs_unattributed_ref_still_crashes_loud(rules):
    """Slicing refs to a shot's cast must not silently swallow a ref that
    belongs to NO cast member (the path-convention guard, locked 2026-07-06) —
    otherwise a typo'd ref path would render nothing and say nothing."""
    refs = [
        "refs/eve/front.png",
        "refs/adam/front.png",
        "render_taste_test/wistoria_refs/will_2_adult.png",  # flat legacy layout
    ]
    with pytest.raises(ValueError, match=r"matches no\s+cast member"):
        _shot_jobs(_scene_package(refs=refs), rules)


def test_shot_jobs_keeps_location_grounding_on_every_shot(rules):
    """REGRESSION GUARD: a location is not a cast member — it must survive the
    per-shot ref slice and be bound on EVERY shot's generation, or the splice
    lane silently renders an ungrounded room (the exact confound that invalidated
    the pitch-47 test; location grounding locked 2026-07-11)."""
    pkg = _single_char_package(["refs/eve/front.png"])
    pkg.world_anchor = "A grand ice-tower chamber, pale marble floor."
    pkg.location_reference_paths = ["refs/_location/elfie_bedroom/room.jpg"]
    jobs = _shot_jobs(pkg, rules)
    assert len(jobs) == 3
    for job in jobs:
        # location ref uploads AFTER the shot's character refs, every shot
        assert job.reference_images == [
            "refs/eve/front.png",
            "refs/_location/elfie_bedroom/room.jpg",
        ]
        assert "A grand ice-tower chamber" in job.prompt
        assert "The setting is shown in image2." in job.prompt


def test_render_jobs_branches_on_scene_lane_mode(rules, monkeypatch):
    """render_jobs dispatches on scene_lane.mode without the caller knowing which
    lane it got (grill Q1). monkeypatch.setitem restores the module-scoped rules
    fixture afterwards — a bare assignment would leak splice mode into every test
    that runs after this one."""
    package = _scene_package()
    assert rules.data["scene_lane"]["mode"] == "single_gen"  # yaml default (Q1)
    assert len(render_jobs(package, rules)) == 1

    monkeypatch.setitem(rules.data["scene_lane"], "mode", "per_scene_splice")
    jobs = render_jobs(package, rules)
    assert len(jobs) == len(package.shots)
    assert all(job.kind == "scene_shot" for job in jobs)
