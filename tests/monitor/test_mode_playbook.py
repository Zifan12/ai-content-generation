"""Tests for the mode playbook loader (src/monitor/mode_playbook.py)."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.monitor.mode_playbook import ModeEntry, load_mode_playbook
from src.monitor.schemas import BeatRole


def test_loads_real_playbook_with_wish_and_satire() -> None:
    """The shipped config parses and yields at least the wish + satire modes."""
    playbook = load_mode_playbook()
    assert {"wish", "satire"} <= set(playbook)
    assert all(isinstance(entry, ModeEntry) for entry in playbook.values())


def test_real_playbook_arcs_use_only_legal_roles() -> None:
    """Every arc value in the shipped config is a legal BeatRole."""
    legal = {role.value for role in BeatRole}
    playbook = load_mode_playbook()
    for entry in playbook.values():
        assert set(entry.arc) <= legal


def test_illegal_arc_role_raises(tmp_path: Path) -> None:
    """An arc containing an unknown role (climax) fails validation at load."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "wish:\n"
        "  description: x\n"
        "  arc: [hook, climax]\n"
        "  craft_emphasis: x\n"
        "  example_logline: x\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_mode_playbook(bad)


def test_missing_required_field_raises(tmp_path: Path) -> None:
    """An entry missing craft_emphasis fails validation at load."""
    bad = tmp_path / "missing.yaml"
    bad.write_text(
        "wish:\n"
        "  description: x\n"
        "  arc: [hook]\n"
        "  example_logline: x\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_mode_playbook(bad)
