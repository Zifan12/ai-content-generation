"""
Pure path/sharding helpers for the archive layout.

No I/O. The archive shards items into 256-ish top-level dirs keyed by the
first two characters of the TikTok video id, dodging the Windows
too-many-entries-in-one-dir wall when the corpus reaches ~100K items.
"""

from pathlib import Path

METADATA_NAME = "metadata.json"
VIDEO_NAME = "video.mp4"
SUBS_NAME = "subs.en.vtt"
THUMB_NAME = "thumb.jpg"


def shard_for(video_id: str) -> str:
    """
    Return the 2-char shard directory name for a video id.

    Uses the first two characters of the id. Ids shorter than two chars are
    right-padded with '_' so the shard name is always exactly two characters.

    Args:
        video_id: TikTok video id (apidojo ``id`` field).

    Returns:
        Two-character shard name.
    """
    return (video_id + "__")[:2]


def item_dir(root: Path, video_id: str) -> Path:
    """
    Return the directory that holds one item's files: root/<shard>/<video_id>.

    Args:
        root: archive root (e.g. ``D:\\tiktok_archive``).
        video_id: TikTok video id.

    Returns:
        Path to the item's folder. Not created here.
    """
    return root / shard_for(video_id) / video_id
