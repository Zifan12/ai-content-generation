"""Voice-profile access + the dialogue-floor rule (decision Q3-B, spec 2026-07-11).

A voice profile is a standing per-character asset at ``refs/<slug>/voice_profile.md``
describing how a character speaks. This module is the read side + the deterministic
gate; the profiles are WRITTEN by ``scripts/gen_voice_profile.py``. No LLM, no
network here — pure functions over the refs library and a pitch.
"""

from pathlib import Path

from src.generation.render_adapters.adapter import _slug
from src.monitor.schemas import StoryPitch

_PROFILE_FILENAME = "voice_profile.md"
_REFS_ROOT = Path("refs")


def load_cast_profiles(refs_root: Path = _REFS_ROOT) -> dict[str, str]:
    """Load every character voice profile in the refs library.

    Scans ``refs_root`` for ``<slug>/voice_profile.md`` files, skipping the
    ``_location`` subtree (locations are not cast members). The returned mapping
    is ``{slug: profile_markdown}``; an empty dict if the library has none.

    Args:
        refs_root: The reference-library root (default ``refs/``).

    Returns:
        Mapping of character slug to the raw markdown of its voice profile.
    """
    profiles: dict[str, str] = {}
    if not refs_root.is_dir():
        return profiles
    for folder in sorted(refs_root.iterdir()):
        if not folder.is_dir() or folder.name == "_location":
            continue
        profile = folder / _PROFILE_FILENAME
        if profile.is_file():
            profiles[folder.name] = profile.read_text(encoding="utf-8")
    return profiles


def format_cast_voices(profiles: dict[str, str]) -> str:
    """Render loaded profiles as the ``<cast_voices>`` prompt block.

    Returns an empty string when no profiles exist, so the caller can append it
    unconditionally and get an empty (harmless) block for an unprofiled cast.

    Args:
        profiles: Mapping of slug to profile markdown (from load_cast_profiles).

    Returns:
        A single ``<cast_voices>...</cast_voices>`` string, or "" if empty.
    """
    if not profiles:
        return ""
    blocks = [f"### {slug}\n{text.strip()}" for slug, text in profiles.items()]
    return "<cast_voices>\n" + "\n\n".join(blocks) + "\n</cast_voices>"


def profiled_names_in_pitch(pitch: StoryPitch, cast_slugs: set[str]) -> set[str]:
    """Return the in-frame character names in this pitch that have a profile.

    A character counts if it appears in any beat's ``characters_in_frame`` AND its
    slug is in ``cast_slugs``.

    Args:
        pitch: The StoryPitch to scan.
        cast_slugs: Slugs of characters that have a voice profile.

    Returns:
        The set of matching character names (empty if none are profiled).
    """
    names: set[str] = set()
    for beat in pitch.beats:
        for name in beat.characters_in_frame:
            if _slug(name) in cast_slugs:
                names.add(name)
    return names


def check_dialogue_floor(pitch: StoryPitch, cast_slugs: set[str]) -> tuple[bool, str | None]:
    """Deterministic dialogue floor (decision Q3-B).

    If a profiled character appears on screen, at least one beat must carry a
    ``dialogue_line`` spoken by a profiled character. If no profiled character is
    on screen, silence is allowed (pass).

    Semantics are ANY, not EACH (decision Q3-B): one profiled speaker with a line
    satisfies the floor for the whole pitch — it does NOT require every profiled
    on-screen character to speak. The ≤2-dialogue-beats ceiling is NOT enforced
    here; it is a soft prompt-side guide (story_pitcher rule 8) by design (Q6 =
    "small": the only deterministic gate is this floor).

    Args:
        pitch: The StoryPitch to check.
        cast_slugs: Slugs of characters that have a voice profile.

    Returns:
        ``(True, None)`` if the floor is satisfied (or does not apply); otherwise
        ``(False, reason)`` where reason names a profiled character that should
        speak — suitable as repair failure notes.
    """
    profiled = profiled_names_in_pitch(pitch, cast_slugs)
    if not profiled:
        return True, None
    for beat in pitch.beats:
        if beat.dialogue_line is not None and beat.speaker is not None:
            if _slug(beat.speaker) in cast_slugs:
                return True, None
    who = ", ".join(sorted(profiled))
    return (
        False,
        f"A profiled character is on screen ({who}) but no beat has a dialogue_line "
        f"spoken by them. Give one of them a single short in-character line "
        f"(<=13 words) on the beat where it lands hardest.",
    )
