from pathlib import Path

from scripts.archive.paths import (
    METADATA_NAME,
    SUBS_NAME,
    THUMB_NAME,
    VIDEO_NAME,
    item_dir,
    shard_for,
)


def test_shard_for_first_two_chars():
    assert shard_for("7382910abc") == "73"


def test_shard_for_short_id_padded():
    assert shard_for("7") == "7_"


def test_item_dir_joins_root_shard_id():
    root = Path("/archive")
    assert item_dir(root, "7382910abc") == root / "73" / "7382910abc"


def test_media_name_constants():
    assert METADATA_NAME == "metadata.json"
    assert VIDEO_NAME == "video.mp4"
    assert SUBS_NAME == "subs.en.vtt"
    assert THUMB_NAME == "thumb.jpg"
