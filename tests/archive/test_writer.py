import json

from scripts.archive.paths import METADATA_NAME, VIDEO_NAME, item_dir
from scripts.archive.writer import archive_item


def _raw_item():
    return {
        "id": "7382910abc",
        "views": 120000,
        "likes": 4300,
        "comments": 50,
        "shares": 12,
        "bookmarks": 7,
        "hashtags": ["aisurreal", "weirdcore"],
        "channel": {"username": "someuser"},
        "video": {"url": "https://cdn/video.mp4", "cover": "https://cdn/cover.jpg"},
        "subtitleInformation": [
            {"language_code": "en-US", "url": "https://cdn/sub.vtt"},
            {"language_code": "es", "url": "https://cdn/es.vtt"},
        ],
    }


def test_archive_item_success_writes_metadata_and_record(tmp_path):
    # downloader that always succeeds, recording the urls it was asked for
    calls = []

    def fake_dl(url, target, timeout=60.0):
        calls.append((url, target.name))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        return True

    ok, record = archive_item(tmp_path, _raw_item(), "surreal_hyperreal", fake_dl)

    assert ok is True
    d = item_dir(tmp_path, "7382910abc")
    meta = json.loads((d / METADATA_NAME).read_text(encoding="utf-8"))
    assert meta["id"] == "7382910abc"
    assert record["id"] == "7382910abc"
    assert record["niche"] == "surreal_hyperreal"
    assert record["path"] == "73/7382910abc"
    assert record["video"] is True
    assert record["subs"] is True
    assert record["thumb"] is True
    assert record["views"] == 120000
    assert record["author"] == "someuser"
    assert record["hashtags"] == ["aisurreal", "weirdcore"]
    assert "scraped_at" in record
    # picked the english subtitle url, not spanish
    assert ("https://cdn/sub.vtt", VIDEO_NAME) not in calls
    assert any(url == "https://cdn/sub.vtt" for url, _ in calls)
    assert all(url != "https://cdn/es.vtt" for url, _ in calls)


def test_archive_item_video_failure_is_critical(tmp_path):
    def fail_video(url, target, timeout=60.0):
        if target.name == VIDEO_NAME:
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        return True

    ok, record = archive_item(tmp_path, _raw_item(), "surreal_hyperreal", fail_video)
    assert ok is False
    assert record["video"] is False
    assert record["stage"] == "video_download"
    # metadata still written even on failure (cheap index)
    meta_path = item_dir(tmp_path, "7382910abc") / METADATA_NAME
    assert meta_path.exists()


def test_archive_item_missing_optional_media(tmp_path):
    raw = _raw_item()
    raw["subtitleInformation"] = []
    raw["video"].pop("cover")

    def ok_dl(url, target, timeout=60.0):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        return True

    ok, record = archive_item(tmp_path, raw, "n", ok_dl)
    assert ok is True
    assert record["video"] is True
    assert record["subs"] is False
    assert record["thumb"] is False
