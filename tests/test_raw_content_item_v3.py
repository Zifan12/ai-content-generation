import pytest

from src.models.trend import RawContentItem


def test_new_fields_exist_with_defaults():
    item = RawContentItem(
        platform="tiktok",
        platform_content_id="7000000000000000000",
        url="https://www.tiktok.com/@x/video/7000000000000000000",
    )
    assert item.collect_count == 0 or item.collect_count is None  # default applied on flush
    assert item.video_download_url is None
    assert item.video_aspect_ratio is None
    assert item.author_tiktok_id is None
    assert item.poi_name is None
    assert item.poi_country is None
    assert item.input_source is None
    assert item.raw_apify_payload is None
    assert item.music_audio_url is None


def test_music_is_original_true_when_artist_matches_username():
    item = RawContentItem(
        platform="tiktok",
        platform_content_id="1",
        url="https://x.example/1",
        author_username="aigrowthlab3",
        raw_apify_payload={"song": {"artist": "aigrowthlab3"}},
    )
    assert item.music_is_original is True


def test_music_is_original_true_case_insensitive():
    item = RawContentItem(
        platform="tiktok",
        platform_content_id="1",
        url="https://x.example/1",
        author_username="AIGrowthLab",
        raw_apify_payload={"song": {"artist": "aigrowthlab"}},
    )
    assert item.music_is_original is True


def test_music_is_original_false_when_artist_differs():
    item = RawContentItem(
        platform="tiktok",
        platform_content_id="1",
        url="https://x.example/1",
        author_username="user1",
        raw_apify_payload={"song": {"artist": "Azure Glitch"}},
    )
    assert item.music_is_original is False


def test_music_is_original_none_when_payload_missing():
    item = RawContentItem(
        platform="tiktok",
        platform_content_id="1",
        url="https://x.example/1",
        author_username="user1",
        raw_apify_payload=None,
    )
    assert item.music_is_original is None


def test_music_is_original_none_when_song_artist_missing():
    item = RawContentItem(
        platform="tiktok",
        platform_content_id="1",
        url="https://x.example/1",
        author_username="user1",
        raw_apify_payload={"song": {}},
    )
    assert item.music_is_original is None