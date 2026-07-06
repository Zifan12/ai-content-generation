"""Tests for src/reference/youtube_client.py — all offline via mocked yt_dlp
and httpx. yt-dlp is invoked via its Python API only (never subprocess)."""

from unittest.mock import MagicMock, patch

import httpx

from src.reference.schemas import VideoCandidate
from src.reference.youtube_client import enrich_candidate, search_youtube

FLAT_SEARCH_INFO = {
    "entries": [
        {
            "id": "abc123",
            "url": "https://www.youtube.com/watch?v=abc123",
            "title": "Stellar Blade Eve Official Trailer",
            "channel": "PlayStation",
            "duration": 92.0,
            "view_count": 500000,
        },
        {
            "id": "def456",
            "url": "https://www.youtube.com/watch?v=def456",
            "title": "Stellar Blade Character Showcase",
            "channel": "PlayStation",
            "duration": 60.0,
            "view_count": 100000,
        },
    ]
}


def _make_fake_ydl(info: dict) -> MagicMock:
    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value = fake_ydl
    fake_ydl.__exit__.return_value = False
    fake_ydl.extract_info.return_value = info
    return fake_ydl


def test_search_youtube_maps_flat_entries_to_video_candidates():
    fake_ydl = _make_fake_ydl(FLAT_SEARCH_INFO)
    with patch("src.reference.youtube_client.yt_dlp.YoutubeDL", return_value=fake_ydl):
        candidates = search_youtube("stellar blade eve trailer", limit=8)

    assert len(candidates) == 2
    first = candidates[0]
    assert isinstance(first, VideoCandidate)
    assert first.video_id == "abc123"
    assert first.title == "Stellar Blade Eve Official Trailer"
    assert first.channel == "PlayStation"
    assert first.duration_seconds == 92.0
    assert first.view_count == 500000
    assert first.transcript_excerpt is None

    # search performs no download, ever.
    call_kwargs = fake_ydl.extract_info.call_args
    assert call_kwargs.kwargs.get("download") is False


def test_search_youtube_empty_entries_returns_empty_list():
    fake_ydl = _make_fake_ydl({"entries": []})
    with patch("src.reference.youtube_client.yt_dlp.YoutubeDL", return_value=fake_ydl):
        candidates = search_youtube("no results query", limit=8)

    assert candidates == []


def _base_candidate(**overrides: object) -> VideoCandidate:
    defaults = {
        "video_id": "abc123",
        "url": "https://www.youtube.com/watch?v=abc123",
        "title": "Stellar Blade Eve Official Trailer",
        "channel": "PlayStation",
        "duration_seconds": 92.0,
        "view_count": 500000,
        "description": "",
        "transcript_excerpt": None,
    }
    defaults.update(overrides)
    return VideoCandidate(**defaults)


def test_enrich_candidate_fetches_description_and_transcript():
    full_info = {
        "id": "abc123",
        "description": "The official reveal trailer for Eve.",
        "subtitles": {
            "en": [{"ext": "vtt", "url": "https://example.com/subs.vtt"}],
        },
        "automatic_captions": {},
    }
    fake_ydl = _make_fake_ydl(full_info)
    vtt_body = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\n"
        "Eve draws her blade.\n\n"
        "00:00:02.000 --> 00:00:04.000\n"
        "Eve draws her blade.\n\n"  # duplicate segment, must be deduped
        "00:00:04.000 --> 00:00:06.000\n"
        "The city falls silent.\n"
    )
    fake_response = MagicMock()
    fake_response.text = vtt_body
    fake_response.raise_for_status.return_value = None
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.get.return_value = fake_response

    with patch("src.reference.youtube_client.yt_dlp.YoutubeDL", return_value=fake_ydl), \
        patch("src.reference.youtube_client.httpx.Client", return_value=fake_client):
        enriched = enrich_candidate(_base_candidate())

    assert enriched.description == "The official reveal trailer for Eve."
    assert enriched.transcript_excerpt == "Eve draws her blade. The city falls silent."
    # Returns a NEW instance; does not mutate the input.
    assert enriched is not _base_candidate()


def test_enrich_candidate_truncates_long_transcript():
    long_line = "word " * 1000
    full_info = {
        "id": "abc123",
        "description": "x",
        "subtitles": {"en": [{"ext": "vtt", "url": "https://example.com/subs.vtt"}]},
        "automatic_captions": {},
    }
    fake_ydl = _make_fake_ydl(full_info)
    vtt_body = f"WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n{long_line}\n"
    fake_response = MagicMock()
    fake_response.text = vtt_body
    fake_response.raise_for_status.return_value = None
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.get.return_value = fake_response

    with patch("src.reference.youtube_client.yt_dlp.YoutubeDL", return_value=fake_ydl), \
        patch("src.reference.youtube_client.httpx.Client", return_value=fake_client):
        enriched = enrich_candidate(_base_candidate())

    assert enriched.transcript_excerpt is not None
    assert len(enriched.transcript_excerpt) <= 1500


def test_enrich_candidate_missing_subtitles_gives_none_excerpt():
    full_info = {
        "id": "abc123",
        "description": "x",
        "subtitles": {},
        "automatic_captions": {},
    }
    fake_ydl = _make_fake_ydl(full_info)
    with patch("src.reference.youtube_client.yt_dlp.YoutubeDL", return_value=fake_ydl):
        enriched = enrich_candidate(_base_candidate())

    assert enriched.transcript_excerpt is None


def test_enrich_candidate_http_error_gives_none_excerpt():
    full_info = {
        "id": "abc123",
        "description": "x",
        "subtitles": {"en": [{"ext": "vtt", "url": "https://example.com/subs.vtt"}]},
        "automatic_captions": {},
    }
    fake_ydl = _make_fake_ydl(full_info)
    fake_client = MagicMock()
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False
    fake_client.get.side_effect = httpx.HTTPError("boom")

    with patch("src.reference.youtube_client.yt_dlp.YoutubeDL", return_value=fake_ydl), \
        patch("src.reference.youtube_client.httpx.Client", return_value=fake_client):
        enriched = enrich_candidate(_base_candidate())

    assert enriched.transcript_excerpt is None
