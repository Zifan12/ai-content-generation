"""
Mode playbook loader.

Loads ``config/mode_playbook.yaml`` — the growable library of content modes
(``wish``, ``satire``) defined in the reaction-driven spec (06-27 §2) — into
validated :class:`ModeEntry` objects. Adding a new mode is a YAML edit, not a
code change; this loader is the thin validation layer that turns that data into
typed objects and fails loud at load time.

Each entry carries: a description of the pattern, the ordered beat-role ``arc``
it follows, the craft emphasis that makes it land, and an example logline. The
load-time validation is the whole point — a typo'd arc role (e.g. ``climax``)
or a missing field must raise here, on startup, rather than silently producing a
broken pitch several stages downstream.

Consumed later by ``StoryPitcher`` and ``StoryCraftGate``, which inject the
playbook entries into their prompts.
"""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

from src.monitor.schemas import BeatRole

DEFAULT_PLAYBOOK_PATH = Path("config/mode_playbook.yaml")


class ModeEntry(BaseModel):
    """
    One content mode from the playbook.

    Fields:
        description: What the pattern is and when it applies.
        arc: Ordered beat roles the mode's story follows. Every value MUST be a
            legal beat role — hook, establish, build, turn, escalate, reveal,
            payoff, tag — enforced by the validation in the TODO below.
        craft_emphasis: The single craft rule that makes this mode land.
        example_logline: A concrete example pitch written in this mode.
    """

    description: str
    arc: list[str]
    craft_emphasis: str
    example_logline: str

    @field_validator("arc")
    @classmethod
    def _arc_roles_are_legal(cls, v: list[str]) -> list[str]:
        """
        Reject any arc entry that is not a legal beat role.

        BeatRole (in schemas.py) is the single source of truth for the eight
        roles; this raises so a typo'd playbook (e.g. ``climax``) fails at load
        time rather than corrupting a pitch several stages downstream.
        """
        legal = {role.value for role in BeatRole}
        illegal = [role for role in v if role not in legal]
        if illegal:
            raise ValueError(
                f"illegal beat role(s) {illegal}; legal roles: {sorted(legal)}"
            )
        return v


def load_mode_playbook(
    path: str | Path = DEFAULT_PLAYBOOK_PATH,
) -> dict[str, ModeEntry]:
    """
    Load and validate the mode playbook.

    Reads the YAML at ``path``, constructs a :class:`ModeEntry` per top-level
    entry, and returns a dict keyed by mode name (``"wish"``, ``"satire"``).
    Each ``ModeEntry(**entry)`` runs the field validation (including the arc-role
    check you implement above), so a malformed entry raises here.

    Args:
        path: Path to the playbook YAML. Defaults to ``config/mode_playbook.yaml``.

    Returns:
        Mapping of mode name to its validated :class:`ModeEntry`.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        pydantic.ValidationError: If any entry has an illegal arc role or is
            missing a required field.
    """
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return {name: ModeEntry(**entry) for name, entry in raw.items()}
