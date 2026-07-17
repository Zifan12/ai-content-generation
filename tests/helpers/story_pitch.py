"""Shared StoryScript builder for pipeline/smoke tests (v3 multi-shot era).

Slice ① (staged director, 2026-07-16): the story container is StoryScript —
same shape the old StoryPitch had minus the deleted caption_policy/hook_line
pair. The builder keeps its historical name; callers are unchanged.
"""

from src.monitor.schemas import (
    BeatRole,
    CharacterRef,
    ContentMode,
    ShotSize,
    StoryBeat,
    StoryScript,
)

_SIZES = [
    ShotSize.establishing,
    ShotSize.medium,
    ShotSize.close_up,
    ShotSize.wide,
    ShotSize.over_shoulder,
    ShotSize.extreme_close_up,
]


def build_story_pitch(
    n_beats: int = 3,
    narrations: list[str | None] | None = None,
) -> StoryScript:
    """Return a schema-valid StoryScript with n_beats beats (varied shot sizes,
    one character)."""
    if narrations is None:
        narrations = ["Narration line."] * n_beats
    beats = [
        StoryBeat(
            role=BeatRole.hook if i == 0 else BeatRole.build,
            visual_line=f"Beat {i}: the swordswoman advances through the rain.",
            narration_line=narrations[i],
            shot_size=_SIZES[i % len(_SIZES)],
            characters_in_frame=["Eve"],
            hero_moment=False,
        )
        for i in range(n_beats)
    ]
    return StoryScript(
        logline="Eve gets the ending the fans wanted.",
        mode=ContentMode.wish,
        characters=[CharacterRef(name="Eve", ip_source="Stellar Blade")],
        desired_moment="The confrontation the trailer denied.",
        beats=beats,
        why_it_lands="Fans are begging for exactly this beat.",
        legal_flag=False,
    )
