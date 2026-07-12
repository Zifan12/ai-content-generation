from pathlib import Path

from src.monitor.schemas import (
    CaptionPolicy,
    CharacterRef,
    ShotSize,
    StoryBeat,
    StoryPitch,
)
from src.monitor.voice_profiles import (
    check_dialogue_floor,
    format_cast_voices,
    load_cast_profiles,
    profiled_names_in_pitch,
)


def _beat(role, size, cast, dialogue=None, speaker=None) -> StoryBeat:
    return StoryBeat(
        role=role,
        visual_line="v",
        narration_line=None,
        dialogue_line=dialogue,
        speaker=speaker,
        shot_size=size,
        characters_in_frame=cast,
        hero_moment=(role == "payoff"),
    )


def _pitch(beats: list[StoryBeat], characters: list[CharacterRef]) -> StoryPitch:
    return StoryPitch(
        logline="l",
        mode="wish",
        characters=characters,
        desired_moment="m",
        scene_setting="a room, now",
        beats=beats,
        caption_policy=CaptionPolicy.none,
        hook_line=None,
        why_it_lands="w",
        legal_flag=False,
    )


# Minimum-legal beat trio: 3 beats, two distinct shot sizes, one payoff (hero_moment).
def _elfaria_pitch(dialogue=None, speaker=None) -> StoryPitch:
    cast = ["Elfaria Albis Serfort"]
    return _pitch(
        beats=[
            _beat("establish", ShotSize.wide, cast),
            _beat("build", ShotSize.medium, cast),
            _beat("payoff", ShotSize.close_up, cast, dialogue=dialogue, speaker=speaker),
        ],
        characters=[CharacterRef(name="Elfaria Albis Serfort", ip_source="Wistoria")],
    )


def test_load_cast_profiles_reads_md_and_skips_location(tmp_path: Path):
    (tmp_path / "elfaria").mkdir()
    (tmp_path / "elfaria" / "voice_profile.md").write_text("## Fingerprint\nclipped", encoding="utf-8")
    (tmp_path / "will").mkdir()  # no profile -> not loaded
    (tmp_path / "_location" / "room").mkdir(parents=True)
    (tmp_path / "_location" / "room" / "voice_profile.md").write_text("nope", encoding="utf-8")

    profiles = load_cast_profiles(tmp_path)

    assert set(profiles) == {"elfaria"}
    assert "clipped" in profiles["elfaria"]


def test_load_cast_profiles_missing_root_is_empty(tmp_path: Path):
    assert load_cast_profiles(tmp_path / "does_not_exist") == {}


def test_format_cast_voices_empty_is_blank():
    assert format_cast_voices({}) == ""


def test_format_cast_voices_wraps_each_profile():
    block = format_cast_voices({"elfaria": "## Fingerprint\nclipped"})
    assert block.startswith("<cast_voices>")
    assert "### elfaria" in block
    assert "clipped" in block


def test_profiled_names_in_pitch_matches_by_slug():
    pitch = _pitch(
        beats=[
            _beat("establish", ShotSize.wide, ["Elfaria Albis Serfort"]),
            _beat("build", ShotSize.medium, ["Zeo"]),
            _beat("payoff", ShotSize.close_up, ["Elfaria Albis Serfort", "Zeo"]),
        ],
        characters=[
            CharacterRef(name="Elfaria Albis Serfort", ip_source="X"),
            CharacterRef(name="Zeo", ip_source="X"),
        ],
    )
    assert profiled_names_in_pitch(pitch, {"elfaria_albis_serfort"}) == {"Elfaria Albis Serfort"}


def test_floor_passes_when_no_profiled_character_on_screen():
    zeo = ["Zeo"]
    pitch = _pitch(
        beats=[
            _beat("establish", ShotSize.wide, zeo),
            _beat("build", ShotSize.medium, zeo),
            _beat("payoff", ShotSize.close_up, zeo),
        ],
        characters=[CharacterRef(name="Zeo", ip_source="X")],
    )
    ok, reason = check_dialogue_floor(pitch, cast_slugs=set())
    assert ok is True and reason is None


def test_floor_fails_when_profiled_character_is_silent():
    ok, reason = check_dialogue_floor(_elfaria_pitch(), cast_slugs={"elfaria_albis_serfort"})
    assert ok is False
    assert "Elfaria Albis Serfort" in reason


def test_floor_passes_when_profiled_character_speaks():
    pitch = _elfaria_pitch(dialogue="You are late, again.", speaker="Elfaria Albis Serfort")
    ok, reason = check_dialogue_floor(pitch, cast_slugs={"elfaria_albis_serfort"})
    assert ok is True and reason is None
