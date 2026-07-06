"""
Guarded video download + scene-guided frame extraction for the reference
harvester.

Mirrors two existing patterns:
- Download guards: OpenMontage ``video_downloader.py``'s metadata-first
  duration check (fetch metadata before ever downloading, reject over-cap
  loud) — here extended with a URL-hash cache skip and a post-download
  validity probe (never trust that yt-dlp wrote a playable file).
- Frame extraction: OpenMontage ``scene_detect.py``'s ffmpeg-fallback scene
  boundary detection (``select='gt(scene,threshold)'`` + ``showinfo``, no
  PySceneDetect dependency) feeding ``frame_sampler.py``'s scene-guided
  timestamp selection (first frame + midpoint per scene longer than 3s,
  deduped/capped).

ffmpeg/ffprobe are invoked via subprocess with LIST argv only — never a shell
string (audit C1 lesson: shell-string subprocess calls are command-injection
surface).
"""

import hashlib
import logging
import re
import subprocess
from pathlib import Path

import cv2  # type: ignore[import-untyped]
import imagehash
import yt_dlp  # type: ignore[import-untyped]
from PIL import Image

from src.reference.schemas import FrameScore

logger = logging.getLogger(__name__)

_SCENE_CHANGE_THRESHOLD = 0.3
_MIN_SCENE_GAP_SECONDS = 1.0
_MIDPOINT_SCENE_MIN_DURATION = 3.0
_SUBPROCESS_TIMEOUT_SECONDS = 60


class DownloadError(RuntimeError):
    """Raised when a candidate exceeds the duration cap or fails the
    post-download validity probe (corrupt/empty file)."""


def _url_hash(url: str) -> str:
    """Stable cache key for a video URL — same URL always maps to the same
    on-disk filename, so a repeat harvest run skips re-downloading."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def download_video(
    url: str,
    dest_dir: Path,
    *,
    max_duration_seconds: int,
    resolution_cap: int,
) -> Path:
    """
    Download a video, guarded by a metadata-first duration re-check, a
    URL-hash cache skip, and a post-download validity probe.

    The picker (Task 6) already saw this candidate's duration and presumably
    picked it because it was within cap — but that metadata could be stale or
    wrong, so this re-checks live, before spending any download time.

    Raises:
        DownloadError: metadata-checked duration exceeds ``max_duration_seconds``,
            or the downloaded file fails its post-download validity probe
            (in which case the corrupt file is deleted before raising).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    video_path = dest_dir / f"{_url_hash(url)}.mp4"
    if video_path.exists():
        return video_path

    with yt_dlp.YoutubeDL(
        {"quiet": True, "no_warnings": True, "skip_download": True}
    ) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    duration = info.get("duration") or 0
    if duration > max_duration_seconds:
        raise DownloadError(
            f"{url} is {duration}s, exceeds max_duration_seconds={max_duration_seconds}"
        )

    ydl_opts = {
        "format": (
            f"bestvideo[height<={resolution_cap}]+bestaudio/"
            f"best[height<={resolution_cap}]/best"
        ),
        "merge_output_format": "mp4",
        "outtmpl": str(video_path),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if not video_path.exists() or _probe_duration(video_path) <= 0:
        if video_path.exists():
            video_path.unlink()
        raise DownloadError(f"Downloaded file for {url} failed validity probe")

    return video_path


def delete_video(video_path: Path) -> None:
    """Delete the downloaded video file. Frames are extracted; the source
    video is not kept (spec: video deleted after extraction, frames +
    manifest kept)."""
    video_path.unlink(missing_ok=True)


def _probe_duration(video_path: Path) -> float:
    """ffprobe's own duration read of a file already on disk — independent of
    whatever yt-dlp's pre-download metadata claimed."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(video_path),
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def extract_frames(video_path: Path, out_dir: Path, *, max_frames: int = 200) -> list[Path]:
    """
    Extract PNG reference frames guided by scene boundaries: the first frame
    of each detected scene, plus a midpoint frame for scenes longer than
    ``_MIDPOINT_SCENE_MIN_DURATION`` seconds. Falls back to an evenly-spaced
    count-based extraction when no scene changes are detected at all (e.g. a
    single continuous shot).

    A letterbox crop (``cropdetect``) is probed once and applied to every
    extracted frame when black bars are detected; when none are found, frames
    are extracted uncropped.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    duration = _probe_duration(video_path)
    scene_starts = _detect_scene_changes(video_path)
    timestamps = _scene_guided_timestamps(scene_starts, duration, max_frames)
    crop = _detect_crop(video_path)

    frame_paths: list[Path] = []
    for i, ts in enumerate(timestamps):
        output_file = out_dir / f"frame_{i:04d}.png"
        cmd = ["ffmpeg", "-y", "-ss", str(ts), "-i", str(video_path), "-frames:v", "1"]
        if crop:
            cmd.extend(["-vf", f"crop={crop}"])
        cmd.append(str(output_file))

        subprocess.run(cmd, capture_output=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS)
        if output_file.exists():
            frame_paths.append(output_file)

    return frame_paths


def _detect_scene_changes(video_path: Path) -> list[float]:
    """ffmpeg select-filter scene detection (no PySceneDetect dependency) —
    returns sorted scene-change timestamps, at least ``_MIN_SCENE_GAP_SECONDS``
    apart. Empty list means no scene changes were detected."""
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vf", f"select='gt(scene,{_SCENE_CHANGE_THRESHOLD})',showinfo",
        "-f", "null", "-",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS
    )

    change_points: list[float] = []
    for match in re.finditer(r"pts_time:(\d+\.?\d*)", result.stderr):
        ts = float(match.group(1))
        if not change_points or ts - change_points[-1] >= _MIN_SCENE_GAP_SECONDS:
            change_points.append(ts)
    return change_points


def _detect_crop(video_path: Path) -> str | None:
    """Probe for a letterbox crop via ffmpeg's ``cropdetect`` filter. Returns
    the last (most stable) detected ``W:H:X:Y`` string, or None when no crop
    is reported (no letterboxing)."""
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vf", "cropdetect=24:16:0",
        "-frames:v", "20",
        "-f", "null", "-",
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS
    )
    matches = re.findall(r"crop=(\d+:\d+:\d+:\d+)", result.stderr)
    return matches[-1] if matches else None


def _scene_guided_timestamps(
    scene_starts: list[float], duration: float, max_frames: int
) -> list[float]:
    """
    Turn scene-change points into extraction timestamps: the first frame of
    each scene (offset +0.1s to avoid a black frame at the exact cut), plus a
    midpoint frame for scenes longer than ``_MIDPOINT_SCENE_MIN_DURATION``.

    No scene changes detected -> falls back to an evenly-spaced count-based
    spread across the video (bounded by ``max_frames``), so a single
    continuous shot still yields usable frames.
    """
    if not scene_starts:
        count = min(max_frames, 15)
        if duration <= 0 or count <= 0:
            return []
        step = duration / count
        return [round(step * (i + 0.5), 3) for i in range(count)]

    boundaries = sorted(scene_starts)
    scene_bounds = list(zip(boundaries, boundaries[1:] + [duration]))

    timestamps: list[float] = []
    for start, end in scene_bounds:
        scene_duration = end - start
        timestamps.append(start + 0.1)
        if scene_duration > _MIDPOINT_SCENE_MIN_DURATION:
            timestamps.append(start + scene_duration / 2)

    timestamps = sorted({round(t, 3) for t in timestamps})
    if len(timestamps) > max_frames:
        step = len(timestamps) / max_frames
        timestamps = [timestamps[int(i * step)] for i in range(max_frames)]

    return timestamps


def _sharpness(gray) -> float:
    """
    Laplacian variance of a grayscale image — a single scalar standing in for
    "how much crisp edge detail is present". The Laplacian is a second-derivative
    edge operator; a sharp frame has strong, varied edge responses (high
    variance), while motion blur or defocus flattens those responses toward a
    constant (low variance). Higher = sharper.
    """
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _luminance(gray) -> float:
    """
    Mean pixel value of a grayscale image on the 0-255 scale — a proxy for
    overall brightness. A frame captured during a fade-to-black or an
    underexposed scene has a low mean and shows the character too dimly to be a
    usable reference.
    """
    return float(gray.mean())


def prefilter(
    frame_paths: list[Path],
    *,
    sharpness_min: float,
    phash_distance_min: int,
    luminance_min: int,
    max_out: int,
) -> list[FrameScore]:
    """
    Cheap local triage of extracted frames before the paid vision judge.

    Runs three rejection/collapse stages in a fixed order (decision D1):

    1. Drop-blurry: reject any frame whose Laplacian-variance sharpness is
       below ``sharpness_min``.
    2. Drop-dark: of the survivors, reject any whose mean luminance is below
       ``luminance_min``.
    3. Collapse near-duplicates: many extracted frames are the same shot held
       for a couple seconds. Frames are sorted sharpest-first, then greedily
       kept only when their perceptual hash (pHash) differs from every
       already-kept frame by at least ``phash_distance_min`` Hamming bits.
       Because the scan runs sharpest-first, the frame retained from any
       near-duplicate cluster is automatically its sharpest member (decision
       D2), and every kept frame is a distinct shot.

    The distinct-shot survivors are then truncated to at most ``max_out``
    (decision D3: the cap counts distinct shots, and since each survivor is
    already one distinct shot, this keeps the ``max_out`` sharpest shots).

    Rejecting blur and darkness BEFORE collapsing duplicates means dedup runs
    over an already-clean set, so a cluster's sharpest survivor is never one
    that a later dark/blur reject would have removed.

    Args:
        frame_paths: PNG frames produced by ``extract_frames``.
        sharpness_min: Laplacian-variance floor; below this = too blurry.
        phash_distance_min: pHash Hamming distance below which two frames are
            treated as the same shot and collapsed.
        luminance_min: mean-luminance floor (0-255); below this = too dark.
        max_out: maximum distinct shots returned.

    Returns:
        FrameScore entries (path + sharpness, verdict left None for the judge
        to fill), ordered sharpest-first. Empty input yields an empty list;
        frames that fail to load are skipped with a warning, never raised.
    """
    scored: list[tuple[float, Path]] = []
    for path in frame_paths:
        gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if gray is None:
            logger.warning("prefilter: could not read frame, skipping: %s", path)
            continue
        sharpness = _sharpness(gray)
        if sharpness < sharpness_min:
            continue
        if _luminance(gray) < luminance_min:
            continue
        scored.append((sharpness, path))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    kept: list[tuple[float, Path]] = []
    kept_hashes: list[imagehash.ImageHash] = []
    for sharpness, path in scored:
        phash = imagehash.phash(Image.open(path))
        if all(phash - h >= phash_distance_min for h in kept_hashes):
            kept.append((sharpness, path))
            kept_hashes.append(phash)
        if len(kept) >= max_out:
            break

    return [FrameScore(path=str(path), sharpness=sharpness) for sharpness, path in kept]
