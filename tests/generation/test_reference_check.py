"""Tests for the pre-render reference check (spec 2026-07-11).

The check derives required references from a pitch (in-frame cast filtered by
needs_reference + the location_slug), verifies them against the shared refs/
library on disk, and reports present/missing without spending or rendering.
Each test chdirs into a tmp refs/ tree so the on-disk checks are hermetic.

build_story_pitch's cast is ["Eve"] in every beat (slug "eve").
"""

from pathlib import Path

from src.generation.reference_check import check_references, render_manifest
from tests.helpers.story_pitch import build_story_pitch


def _layout(tmp_path, *, chars=(), location=None, loc_images=(), loc_desc=False):
    """Build a refs/ tree under tmp_path: chars = {slug: n_images}."""
    for slug, n in dict(chars).items():
        d = tmp_path / "refs" / slug
        d.mkdir(parents=True)
        for i in range(n):
            (d / f"{i}.png").write_bytes(b"x")
    if location is not None:
        d = tmp_path / "refs" / "_location" / location
        d.mkdir(parents=True)
        for name in loc_images:
            (d / name).write_bytes(b"x")
        if loc_desc:
            (d / "world_anchor.txt").write_text("desc", encoding="utf-8")


def test_all_present_is_ready(tmp_path, monkeypatch):
    _layout(tmp_path, chars={"eve": 2}, location="room", loc_images=("a.jpg",), loc_desc=True)
    monkeypatch.chdir(tmp_path)
    m = check_references(build_story_pitch(3), location_slug="room")
    assert m.ready is True
    assert m.character_reference_paths == [
        str(Path("refs/eve/0.png")),
        str(Path("refs/eve/1.png")),
    ]
    assert m.location_reference_paths == [str(Path("refs/_location/room/a.jpg"))]


def test_missing_character_not_ready(tmp_path, monkeypatch):
    _layout(tmp_path, chars={})  # no eve folder
    monkeypatch.chdir(tmp_path)
    m = check_references(build_story_pitch(3), location_slug=None)
    assert m.ready is False
    eve = next(i for i in m.items if i.slug == "eve")
    assert eve.present is False


def test_location_missing_description_not_ready(tmp_path, monkeypatch):
    _layout(tmp_path, chars={"eve": 1}, location="room", loc_images=("a.jpg",), loc_desc=False)
    monkeypatch.chdir(tmp_path)
    m = check_references(build_story_pitch(3), location_slug="room")
    assert m.ready is False
    loc = next(i for i in m.items if i.kind == "location")
    assert loc.has_description is False


def test_no_location_slug_is_character_only(tmp_path, monkeypatch):
    _layout(tmp_path, chars={"eve": 1})
    monkeypatch.chdir(tmp_path)
    m = check_references(build_story_pitch(3), location_slug=None)
    assert all(i.kind == "character" for i in m.items)
    assert m.location_reference_paths == []
    assert m.ready is True


def test_needs_reference_false_character_skipped(tmp_path, monkeypatch):
    _layout(tmp_path, chars={})  # nobody provisioned
    monkeypatch.chdir(tmp_path)
    pitch = build_story_pitch(3)
    for c in pitch.characters:
        c.needs_reference = False
    m = check_references(pitch, location_slug=None)
    assert m.items == []
    assert m.ready is True


def test_render_manifest_mentions_missing(tmp_path, monkeypatch):
    _layout(tmp_path, chars={})
    monkeypatch.chdir(tmp_path)
    text = render_manifest(check_references(build_story_pitch(3), None))
    assert "MISSING" in text
    assert "eve" in text
