"""Tests for TikTokScraper._normalize_item with apidojo payload shape."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.scrapers.tiktok import TikTokScraper


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "apidojo_item.json"


@pytest.fixture
def apidojo_item() -> dict:
    with open(FIXTURE_PATH) as f:
        return json.load(f)


@pytest.fixture
def scraper(tmp_path) -> TikTokScraper:
    # We do not hit the DB inside _normalize_item, so a bare scraper is fine.
    return TikTokScraper(db=None, actor_id="apidojo/tiktok-scraper")


def test_normalize_returns_none_when_id_missing(scraper):
    assert scraper._normalize_item({}, niche_id=None) is None


def test_normalize_extracts_basic_metrics(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=42)
    assert item is not None
    assert item.platform == "tiktok"
    assert item.platform_content_id == "7636793337772608790"
    assert item.niche_id == 42
    assert item.views == 4520
    assert item.likes == 273
    assert item.comments == 12
    assert item.shares == 7
    assert item.collect_count == 28


def test_normalize_extracts_hashtags(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=None)
    assert item.hashtags == sorted(
        ["aigeneratedvideos", "viralvideos", "aiautomation", "ai", "fyp"]
    )


def test_normalize_uses_post_page_as_url(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=None)
    assert item.url == "https://www.tiktok.com/@aigrowthlab3/video/7636793337772608790"


def test_normalize_extracts_channel_fields(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=None)
    assert item.author_username == "aigrowthlab3"
    assert item.author_tiktok_id == "7632744055432840214"


def test_normalize_extracts_video_fields(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=None)
    assert item.duration_in_seconds == 333
    assert item.video_download_url == "https://example.com/video.mp4"
    assert item.video_aspect_ratio == "540p"
    assert item.thumbnail_url == "https://example.com/cover.jpg"


def test_normalize_extracts_song_fields(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=None)
    assert item.audio_id == "7636793420523605000"
    # apidojo does not provide a music stream URL; music_audio_url is None.
    assert item.music_audio_url is None


def test_normalize_extracts_published_at_utc(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=None)
    assert item.published_at == datetime(2026, 5, 6, 14, 58, 35, tzinfo=timezone.utc)


def test_normalize_extracts_description(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=None)
    assert item.description == apidojo_item["title"]


def test_normalize_picks_english_subtitle(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=None)
    assert item.subtitle_url == "https://example.com/subtitles.vtt"


def test_normalize_extracts_poi_minimal(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=None)
    assert item.poi_name == "Benin City Nigeria Temple"
    assert item.poi_country == "2328926"


def test_normalize_captures_input_source(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=None)
    assert item.input_source == "https://www.tiktok.com/tag/ai"


def test_normalize_stores_full_raw_payload(scraper, apidojo_item):
    item = scraper._normalize_item(apidojo_item, niche_id=None)
    assert item.raw_apify_payload == apidojo_item


def test_normalize_handles_missing_optional_fields(scraper):
    minimal = {
        "id": "12345",
        "title": "test",
        "views": 0,
        "likes": 0,
        "comments": 0,
        "shares": 0,
        "bookmarks": 0,
        "hashtags": [],
        "channel": {"username": "user", "id": "999"},
        "uploadedAt": 1700000000,
        "uploadedAtFormatted": "2023-11-14T22:13:20.000Z",
        "video": {},
        "song": {},
        "subtitleInformation": None,
        "postPage": "https://www.tiktok.com/@user/video/12345",
        "poi": None,
    }
    item = scraper._normalize_item(minimal, niche_id=None)
    assert item is not None
    assert item.platform_content_id == "12345"
    assert item.video_download_url is None
    assert item.video_aspect_ratio is None
    assert item.subtitle_url is None
    assert item.poi_name is None
    assert item.poi_country is None
    assert item.input_source is None


def test_normalize_skips_non_english_subtitles(scraper):
    item_data = {
        "id": "1",
        "title": "x",
        "views": 0, "likes": 0, "comments": 0, "shares": 0, "bookmarks": 0,
        "hashtags": [],
        "channel": {"username": "u", "id": "1"},
        "uploadedAt": 1700000000,
        "uploadedAtFormatted": "2023-11-14T22:13:20.000Z",
        "video": {},
        "song": {},
        "subtitleInformation": [
            {"language_code": "zh-Hans", "url": "https://x/zh.vtt", "is_auto_generated": True},
        ],
        "postPage": "https://www.tiktok.com/@u/video/1",
        "poi": None,
    }
    item = scraper._normalize_item(item_data, niche_id=None)
    assert item.subtitle_url is None
