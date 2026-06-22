from datetime import datetime, timezone

import pytest

from src.scrapers.youtube import YoutubeScraper

@pytest.fixture 
def scraper():
    return YoutubeScraper(db=None)


def test_parse_duration_seconds_only(scraper):                                                                   
    assert scraper._parse_duration("PT59S") == 59

def test_parse_duration_minutes_and_seconds(scraper):
    assert scraper._parse_duration("PT1M5S") == 65

def test_parse_duration_full(scraper):
    assert scraper._parse_duration("PT1H2M3S") == 3723

def test_parse_duration_none(scraper):
    assert scraper._parse_duration(None) is None

def test_parse_duration_invalid(scraper):
    assert scraper._parse_duration("Hello") == 0

def test_extract_hashtags(scraper):
    tags = scraper._extract_hashtags(
         title = "Top #AI tricks",
         description="Learn #Python today",
         tags=["Coding", "AI", "ML", "  "],
    )
    assert tags == ["ai", "coding", "ml", "python"]

def test_normalize_video_short(scraper):
    item = {
        "id": "abc123",
        "snippet": {
            "title": "#AI tips",
            "description": "fast #python",
            "publishedAt": "2026-02-20T15:30:00Z",
            "tags": ["ml"],
        },
        "contentDetails": {"duration": "PT45S"},
        "statistics": {"viewCount": "1000", "likeCount": "100", "commentCount": "10"},
    }

    row = scraper._normalize_video(item, niche_id=1)
    assert row is not None
    assert row.platform == "youtube"
    assert row.platform_content_id == "abc123"
    assert row.views == 1000
    assert row.likes == 100
    assert row.comments == 10
    assert row.duration_in_seconds == 45
    assert row.content_format == "short"
    assert row.published_at == datetime(2026, 2, 20, 15, 30, tzinfo=timezone.utc)

def test_normalize_video_filters_long(scraper):
    item = {
        "id": "long1",
        "snippet": {"title": "long video", "description": "", "publishedAt": "2026-02-20T15:30:00Z"},
        "contentDetails": {"duration": "PT2M1S"},
        "statistics": {"viewCount": "10", "likeCount": "1", "commentCount": "0"},
    }
    assert scraper._normalize_video(item, niche_id=None) is None

@pytest.mark.asyncio
async def test_fetch_trending_search_then_videos(monkeypatch, scraper):
    search_response = {
        "items": [
            {"id": {"videoId": "short1"}},
            {"id": {"videoId": "long1"}},
        ]
    }
    videos_response = {
        "items": [
            {
                "id": "short1",
                "snippet": {
                    "title": "#AI tips",
                    "description": "fast #python",
                    "publishedAt": "2026-02-20T15:30:00Z",
                    "tags": ["ml"],
                },
                "contentDetails": {"duration": "PT45S"},
                "statistics": {"viewCount": "1000", "likeCount": "50", "commentCount": "5"},
            },
            {
                "id": "long1",
                "snippet": {
                    "title": "long video",
                    "description": "",
                    "publishedAt": "2026-02-20T12:00:00Z",
                },
                "contentDetails": {"duration": "PT3M"},
                "statistics": {"viewCount": "500", "likeCount": "10", "commentCount": "1"},
            },
        ]
    }

    async def fake_get(client, path, params):
        if path == "/search":
            return search_response
        elif path == "/videos":
            return videos_response

    monkeypatch.setattr(scraper, "_get", fake_get)
    monkeypatch.setattr(scraper, "save_items", lambda items: items)

    results = await scraper.fetch_trending(max_results=10, niche_id=1, query="AI shorts")

    assert len(results) == 1
    assert results[0].platform_content_id == "short1"
    assert results[0].views == 1000
    assert results[0].duration_in_seconds == 45
