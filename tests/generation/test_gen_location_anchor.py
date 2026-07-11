"""Tests for scripts/gen_location_anchor.py — the one-time vision step that
caches a location's world-anchor description from its screencap.

Covers the pure branching that ships without a network call:
  - find_location_image: happy path (first sorted image) + the two loud exits
    (missing folder, no image file)
  - main()'s --force overwrite guard, which must refuse before any paid vision
    call when world_anchor.txt already exists.

The vision call itself (llm_for_seat("location_anchor").parse) is NOT exercised
here — it needs the network and a real key; the guard test stops before it.

Home: tests/generation/ rather than tests/scripts/ — a top-level ``scripts``
package already exists, so a ``tests/scripts`` dir collides under pytest's
namespace-package resolution and breaks ``import scripts.gen_location_anchor``.
"""

import sys

import pytest

from scripts.gen_location_anchor import find_location_image, main


def test_find_location_image_returns_first_sorted(tmp_path):
    folder = tmp_path / "room"
    folder.mkdir()
    (folder / "b_detail.png").write_bytes(b"x")
    (folder / "a_wide.jpg").write_bytes(b"x")
    (folder / "world_anchor.txt").write_text("desc", encoding="utf-8")  # ignored (not an image)

    assert find_location_image(folder) == folder / "a_wide.jpg"


def test_find_location_image_missing_folder_exits(tmp_path):
    with pytest.raises(SystemExit, match="No location folder"):
        find_location_image(tmp_path / "does_not_exist")


def test_find_location_image_no_image_exits(tmp_path):
    folder = tmp_path / "room"
    folder.mkdir()
    (folder / "world_anchor.txt").write_text("desc", encoding="utf-8")  # text only, no image
    with pytest.raises(SystemExit, match="No image file"):
        find_location_image(folder)


def test_main_refuses_overwrite_without_force(tmp_path, monkeypatch):
    # An existing world_anchor.txt must not be clobbered unless --force — the
    # guard fires BEFORE the vision call, so no network/key is needed here.
    folder = tmp_path / "refs" / "_location" / "elfie_bedroom"
    folder.mkdir(parents=True)
    (folder / "room.jpg").write_bytes(b"x")
    (folder / "world_anchor.txt").write_text("hand-curated", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["gen_location_anchor.py", "--slug", "elfie_bedroom"])

    with pytest.raises(SystemExit, match="already exists"):
        main()

    # the existing description is untouched
    assert (folder / "world_anchor.txt").read_text(encoding="utf-8") == "hand-curated"
