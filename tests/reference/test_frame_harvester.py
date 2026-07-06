"""Tests for src/reference/frame_harvester.py — download + frame extraction
halves. All offline: yt_dlp and subprocess (ffmpeg/ffprobe) are mocked."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.reference.frame_harvester import (
    DownloadError,
    _url_hash,
    delete_video,
    download_video,
    extract_frames,
)

URL = "https://youtube.com/watch?v=abc123"


def _make_fake_ydl(info: dict) -> MagicMock:
    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value = fake_ydl
    fake_ydl.__exit__.return_value = False
    fake_ydl.extract_info.return_value = info
    return fake_ydl


def _fake_run(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_download_rejects_over_cap_duration_before_downloading(tmp_path):
    fake_ydl = _make_fake_ydl({"duration": 1000})

    with patch("src.reference.frame_harvester.yt_dlp.YoutubeDL", return_value=fake_ydl):
        with pytest.raises(DownloadError, match="900"):
            download_video(URL, tmp_path, max_duration_seconds=900, resolution_cap=1080)

    # metadata-only check — .download() must never be called on an over-cap video.
    fake_ydl.download.assert_not_called()


def test_download_writes_file_and_probes_valid(tmp_path):
    fake_ydl = _make_fake_ydl({"duration": 90})
    cache_path = tmp_path / f"{_url_hash(URL)}.mp4"

    def fake_download(urls):
        cache_path.write_bytes(b"fake video bytes")

    fake_ydl.download.side_effect = fake_download

    with patch("src.reference.frame_harvester.yt_dlp.YoutubeDL", return_value=fake_ydl), \
        patch("src.reference.frame_harvester.subprocess.run", return_value=_fake_run(stdout="90.0")):
        result_path = download_video(
            URL, tmp_path, max_duration_seconds=900, resolution_cap=1080
        )

    assert result_path == cache_path
    assert result_path.exists()


def test_download_uses_url_hash_cache_skip(tmp_path):
    """A second download_video call for the same URL must skip metadata fetch
    and download entirely once the cached file already exists on disk."""
    cache_path = tmp_path / f"{_url_hash(URL)}.mp4"
    cache_path.write_bytes(b"already downloaded")

    fake_ydl = _make_fake_ydl({"duration": 90})

    with patch("src.reference.frame_harvester.yt_dlp.YoutubeDL", return_value=fake_ydl):
        result_path = download_video(
            URL, tmp_path, max_duration_seconds=900, resolution_cap=1080
        )

    assert result_path == cache_path
    fake_ydl.extract_info.assert_not_called()
    fake_ydl.download.assert_not_called()


def test_download_corrupt_file_deleted_and_raises(tmp_path):
    fake_ydl = _make_fake_ydl({"duration": 90})
    cache_path = tmp_path / f"{_url_hash(URL)}.mp4"

    def fake_download(urls):
        cache_path.write_bytes(b"")  # corrupt/empty output

    fake_ydl.download.side_effect = fake_download

    with patch("src.reference.frame_harvester.yt_dlp.YoutubeDL", return_value=fake_ydl), \
        patch("src.reference.frame_harvester.subprocess.run", return_value=_fake_run(stdout="0.0")):
        with pytest.raises(DownloadError, match="validity"):
            download_video(URL, tmp_path, max_duration_seconds=900, resolution_cap=1080)

    assert not cache_path.exists()


def test_delete_video_removes_file(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"data")

    delete_video(video_path)

    assert not video_path.exists()


def test_delete_video_missing_file_does_not_raise(tmp_path):
    delete_video(tmp_path / "does_not_exist.mp4")  # must not raise


def test_extract_frames_scene_guided_with_crop_applied(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")
    out_dir = tmp_path / "frames"

    call_log: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        call_log.append(cmd)
        joined = " ".join(cmd)
        if "showinfo" in joined:
            # scene-change timestamps at 2.5s, 6.0s, 9.0s within a 10s video
            return _fake_run(stderr="pts_time:2.500 pts_time:6.000 pts_time:9.000")
        if "cropdetect" in joined:
            return _fake_run(stderr="crop=1920:800:0:140")
        if cmd[0] == "ffprobe":
            return _fake_run(stdout="10.0")
        # frame extraction call — simulate ffmpeg writing the output PNG.
        output_file = Path(cmd[-1])
        output_file.write_bytes(b"fake png bytes")
        return _fake_run()

    with patch("src.reference.frame_harvester.subprocess.run", side_effect=fake_run):
        frames = extract_frames(video_path, out_dir, max_frames=20)

    assert len(frames) > 0
    for frame in frames:
        assert frame.suffix == ".png"
        assert frame.exists()

    extraction_calls = [c for c in call_log if "frame_" in " ".join(c)]
    assert extraction_calls
    for cmd in extraction_calls:
        assert "crop=1920:800:0:140" in " ".join(cmd)


def test_extract_frames_deduplicates_and_caps_at_max_frames(tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")
    out_dir = tmp_path / "frames"

    # Many close-together scene changes across a long video — more raw
    # timestamps than max_frames allows, plus duplicate-rounding collisions.
    many_pts = " ".join(f"pts_time:{i * 0.5:.3f}" for i in range(1, 200))

    def fake_run(cmd, **kwargs):
        joined = " ".join(cmd)
        if "showinfo" in joined:
            return _fake_run(stderr=many_pts)
        if "cropdetect" in joined:
            return _fake_run(stderr="")  # no letterboxing detected
        if cmd[0] == "ffprobe":
            return _fake_run(stdout="100.0")
        output_file = Path(cmd[-1])
        output_file.write_bytes(b"fake png bytes")
        return _fake_run()

    with patch("src.reference.frame_harvester.subprocess.run", side_effect=fake_run):
        frames = extract_frames(video_path, out_dir, max_frames=20)

    assert len(frames) <= 20


def test_extract_frames_no_scene_changes_falls_back(tmp_path):
    """No detected scene boundaries must not crash — falls back to a bounded
    count-based extraction instead of returning nothing."""
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")
    out_dir = tmp_path / "frames"

    def fake_run(cmd, **kwargs):
        joined = " ".join(cmd)
        if "showinfo" in joined:
            return _fake_run(stderr="")  # no scene changes detected
        if "cropdetect" in joined:
            return _fake_run(stderr="")
        if cmd[0] == "ffprobe":
            return _fake_run(stdout="30.0")
        output_file = Path(cmd[-1])
        output_file.write_bytes(b"fake png bytes")
        return _fake_run()

    with patch("src.reference.frame_harvester.subprocess.run", side_effect=fake_run):
        frames = extract_frames(video_path, out_dir, max_frames=20)

    assert len(frames) > 0
