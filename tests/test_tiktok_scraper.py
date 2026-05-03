"""Tests for TikTokScraper._normalize_item() — no live HTTP."""
from datetime import datetime, timezone

import pytest

from src.scrapers.tiktok import TikTokScraper


@pytest.fixture
def scraper():
    return TikTokScraper(db=None)


def _item(**overrides):
    """Base valid Apify TikTok item. Override fields as needed."""
    base = {
        "id": "vid123",
        "webVideoUrl": "https://www.tiktok.com/@user/video/vid123",
        "playCount": 10000,
        "diggCount": 500,
        "commentCount": 20,
        "shareCount": 5,
        "musicMeta": {"musicId": "music999"},
        "videoMeta": {"duration": 30},
        "hashtags": [{"name": "fitness"}, {"name": "Gym"}],
        "createTime": 1745000000,
    }
    base.update(overrides)
    return base


def test_normalize_maps_fields_correctly(scraper):
    row = scraper._normalize_item(_item(), niche_id=1)
    assert row is not None
    assert row.platform == "tiktok"
    assert row.platform_content_id == "vid123"
    assert row.url == "https://www.tiktok.com/@user/video/vid123"
    assert row.views == 10000
    assert row.likes == 500
    assert row.comments == 20
    assert row.shares == 5
    assert row.niche_id == 1


def test_normalize_returns_none_when_no_id(scraper):
    item = _item()
    del item["id"]
    assert scraper._normalize_item(item, niche_id=1) is None


def test_normalize_extracts_audio_id(scraper):
    row = scraper._normalize_item(_item(), niche_id=None)
    assert row.audio_id == "music999"


def test_normalize_audio_id_none_when_missing(scraper):
    item = _item()
    del item["musicMeta"]
    row = scraper._normalize_item(item, niche_id=None)
    assert row.audio_id is None


def test_normalize_duration_from_video_meta(scraper):
    row = scraper._normalize_item(_item(), niche_id=None)
    assert row.duration_in_seconds == 30


def test_normalize_duration_none_when_missing(scraper):
    item = _item()
    del item["videoMeta"]
    row = scraper._normalize_item(item, niche_id=None)
    assert row.duration_in_seconds is None


def test_normalize_hashtags_lowercased_and_sorted(scraper):
    item = _item(hashtags=[{"name": "Gym"}, {"name": "fitness"}, {"name": "#WorkOut"}])
    row = scraper._normalize_item(item, niche_id=None)
    assert row.hashtags == ["fitness", "gym", "workout"]


def test_normalize_hashtags_deduped(scraper):
    item = _item(hashtags=[{"name": "gym"}, {"name": "Gym"}])
    row = scraper._normalize_item(item, niche_id=None)
    assert row.hashtags == ["gym"]


def test_normalize_published_at_from_unix_timestamp(scraper):
    row = scraper._normalize_item(_item(createTime=1745000000), niche_id=None)
    expected = datetime.fromtimestamp(1745000000, tz=timezone.utc)
    assert row.published_at == expected


def test_normalize_published_at_none_when_missing(scraper):
    item = _item()
    del item["createTime"]
    row = scraper._normalize_item(item, niche_id=None)
    assert row.published_at is None


def test_normalize_falls_back_to_video_url(scraper):
    item = _item()
    del item["webVideoUrl"]
    item["videoUrl"] = "https://fallback.url/video"
    row = scraper._normalize_item(item, niche_id=None)
    assert row.url == "https://fallback.url/video"


def test_normalize_tolerates_non_numeric_counts(scraper):
    item = _item(playCount=None, diggCount="bad", commentCount="", shareCount=None)
    row = scraper._normalize_item(item, niche_id=None)
    assert row.views == 0
    assert row.likes == 0
    assert row.comments == 0
    assert row.shares == 0

def test_normalize_extracts_description(scraper):
    item = _item(text="Caption text with #hashtag")
    row = scraper._normalize_item(item, niche_id=None)
    assert row.description == "Caption text with #hashtag"

def test_normalize_description_none_when_missing(scraper):
    item = _item()
    item.pop("text", None)
    row = scraper._normalize_item(item, niche_id=None)
    assert row.description is None

def test_normalize_extracts_thumbnail_url(scraper):
    item = _item(videoMeta={"duration": 30, "coverUrl": "https://cdn/thumb.jpg"})
    row = scraper._normalize_item(item, niche_id=None)
    assert row.thumbnail_url == "https://cdn/thumb.jpg"

def test_normalize_extracts_video_url(scraper):
    item = _item(musicMeta={"musicId": "music999", "playUrl": "https://cdn/audio.mp4"})
    row = scraper._normalize_item(item, niche_id=None)
    assert row.video_url == "https://cdn/audio.mp4"


def test_normalize_extracts_author_username(scraper):
    item = _item(authorMeta={"name": "creator_handle"})
    row = scraper._normalize_item(item, niche_id=None)
    assert row.author_username == "creator_handle"

def test_normalize_thumbnail_video_url_none_when_videoMeta_missing(scraper):
    item = _item()
    item.pop("videoMeta", None)
    row = scraper._normalize_item(item, niche_id=None)
    assert row.thumbnail_url is None
    assert row.video_url is None


def test_normalize_author_username_none_when_authorMeta_missing(scraper):
    item = _item()
    item.pop("authorMeta", None)
    row = scraper._normalize_item(item, niche_id=None)
    assert row.author_username is None