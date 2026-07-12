"""Integration-intent test: the dialogue floor as the pitch pipeline applies it.

The pipeline (scripts/pitch_angles.py) ANDs ``check_dialogue_floor`` into the
keep-vs-kill gate. These cases assert the rule's pitch-level behavior on the two
outcomes that matter: a profiled character left silent is rejected; the same
character given a line passes.
"""

from src.monitor.schemas import (
    CaptionPolicy,
    CharacterRef,
    ShotSize,
    StoryBeat,
    StoryPitch,
)
from src.monitor.voice_profiles import check_dialogue_floor


def _mk(dialogue, speaker) -> StoryPitch:
    cast = ["Elfaria Albis Serfort"]
    beats = [
        StoryBeat(role="establish", visual_line="v", narration_line=None,
                  shot_size=ShotSize.wide, characters_in_frame=cast),
        StoryBeat(role="build", visual_line="v", narration_line=None,
                  shot_size=ShotSize.medium, characters_in_frame=cast),
        StoryBeat(role="payoff", visual_line="v", narration_line=None,
                  dialogue_line=dialogue, speaker=speaker, shot_size=ShotSize.close_up,
                  characters_in_frame=cast, hero_moment=True),
    ]
    return StoryPitch(
        logline="l", mode="wish",
        characters=[CharacterRef(name="Elfaria Albis Serfort", ip_source="Wistoria")],
        desired_moment="m", scene_setting="s", beats=beats,
        caption_policy=CaptionPolicy.none, hook_line=None, why_it_lands="w", legal_flag=False,
    )


def test_profiled_silent_pitch_is_rejected_by_floor():
    ok, reason = check_dialogue_floor(_mk(None, None), {"elfaria_albis_serfort"})
    assert not ok
    assert "Elfaria Albis Serfort" in reason


def test_profiled_speaking_pitch_passes_floor():
    ok, _ = check_dialogue_floor(
        _mk("We leave. Now.", "Elfaria Albis Serfort"), {"elfaria_albis_serfort"}
    )
    assert ok
