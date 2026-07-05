"""Assembly: N per-shot clips + narration + optional BGM + hook card -> one video.

The post-production seam (spec 2026-07-04 §3.6, D12): ffmpeg-only, no moviepy.
Adapts the MoneyPrinterTurbo pattern where it fits (per-clip normalize pass, then
concat DEMUXER over the normalized files — their comment: avoids moviepy's
repeated-reencode concat) and diverges where our product differs: no clip looping
or duration-fitting (clip lengths are authored per beat; narration fits the shot,
never vice versa), straight cuts only (match-cuts are AUTHORED in the prompts —
assembly adds no transitions).

Stages, all subprocess boundaries injected for tests:

  1. NORMALIZE  — each clip re-encoded once to a common format (1080x1920 padded,
                  30fps, aac 48k) so the concat demuxer can stream-copy.
  2. CONCAT     — concat demuxer over the normalized clips, -c copy.
  3. NARRATION  — TTS one file per narrated shot; each is delayed to its shot's
                  cumulative start offset (code arithmetic from the package's
                  authored durations). Overrun (narration longer than its shot)
                  WARNS, never fails — the writer's word budget is the real fix.
  4. MIX + HOOK — one filter_complex pass: native clip audio (the diegetic SFX
                  bed, 1.0) + narrations (1.0) + optional BGM (0.2, 3s fade-out)
                  via amix; hook card burned with drawtext for the first 2.5s
                  (D9 — the render-side "no baked text" constraint is not
                  violated: this happens AFTER rendering, in the edit).

BGM note: ``bgm_path`` is a ready audio FILE. Generating it from
``package.music_brief`` (Sonilo) is NOT wired here — Sonilo cost is unmeasured
(spec §6.4); generate manually / in the smoke script until it is.
"""

import subprocess
from pathlib import Path

from src.generation.executor import PackageRenderResult
from src.providers.tts.base import TTSProvider
from src.schemas.generation import MultiShotPackage

# Output canvas: TikTok vertical.
_CANVAS = "1080:1920"
_FPS = 30
_BGM_VOLUME = 0.2
_BGM_FADE_SECONDS = 3
_HOOK_SECONDS = 2.5
# Windows system font for the hook card (drawtext needs a fontfile on Windows;
# the evie spike burned its caption card on this machine the same way).
_FONTFILE = "C\\:/Windows/Fonts/arialbd.ttf"


def _run_ffmpeg(argv: list[str]) -> None:
    """Run ffmpeg/ffprobe-style argv, raising loudly on failure."""
    subprocess.run(argv, capture_output=True, text=True, check=True)


def _probe_duration(path: str) -> float:
    """Return a media file's duration in seconds via ffprobe (0.0 on failure —
    duration checks are advisory warnings, never fatal)."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                path,
            ],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return float(out)
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return 0.0


def _escape_drawtext(text: str) -> str:
    """Escape the characters ffmpeg's drawtext filter treats specially."""
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _shot_start_offsets(package: MultiShotPackage) -> list[int]:
    """Cumulative start offset (ms) of each shot from the authored durations."""
    offsets, elapsed = [], 0
    for shot in package.shots:
        offsets.append(elapsed * 1000)
        elapsed += shot.duration_seconds
    return offsets


def assemble(
    result: PackageRenderResult,
    package: MultiShotPackage,
    out_path: str,
    *,
    tts: TTSProvider,
    bgm_path: str | None = None,
    run_ffmpeg=_run_ffmpeg,
    probe_duration=_probe_duration,
) -> str:
    """Assemble rendered clips into the final posted video. Returns out_path.

    Args:
        result: The executor's output — clips in shot-group order (each clip's
            shot_indices say which package shots it covers).
        package: The writer's package — authored durations (narration offsets),
            narration lines, hook_text.
        out_path: Final mp4 path.
        tts: Narration synthesizer (one file per narrated shot).
        bgm_path: Optional ready-made BGM audio file (see module note).
        run_ffmpeg: Injected ffmpeg runner (argv -> None, raises on failure).
        probe_duration: Injected (path) -> seconds prober for overrun warnings.

    Raises:
        ValueError: if the executor result carries no clips.
    """
    if not result.clips:
        raise ValueError("no clips to assemble — did the render run?")

    out_file = Path(out_path)
    work = out_file.parent / "_assembly"
    work.mkdir(parents=True, exist_ok=True)

    # 1. NORMALIZE each clip to a common stream format.
    normalized: list[str] = []
    for i, clip in enumerate(result.clips):
        norm = str(work / f"norm_{i}.mp4")
        run_ffmpeg([
            "ffmpeg", "-y", "-i", clip.clip_path,
            "-vf",
            f"scale={_CANVAS}:force_original_aspect_ratio=decrease,"
            f"pad={_CANVAS}:(ow-iw)/2:(oh-ih)/2,fps={_FPS}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", "2",
            norm,
        ])
        normalized.append(norm)

    # 2. CONCAT via demuxer, stream copy (MoneyPrinterTurbo video.py pattern).
    list_file = work / "concat.txt"
    list_file.write_text(
        "".join(f"file '{Path(p).as_posix()}'\n" for p in normalized),
        encoding="utf-8",
    )
    concat_path = str(work / "concat.mp4")
    run_ffmpeg([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", concat_path,
    ])

    # 3. NARRATION per narrated shot, delayed to its shot's start offset.
    offsets = _shot_start_offsets(package)
    narrations: list[tuple[str, int]] = []  # (audio path, delay ms)
    for i, shot in enumerate(package.shots):
        if shot.narration_line is None:
            continue
        narr_path = tts.synthesize(shot.narration_line, str(work / f"narr_{i}.mp3"))
        spoken = probe_duration(narr_path)
        if spoken > shot.duration_seconds:
            print(
                f"WARNING: shot {i} narration runs {spoken:.1f}s over its "
                f"{shot.duration_seconds}s shot — tighten the writer's word budget."
            )
        narrations.append((narr_path, offsets[i]))

    # 4. MIX + HOOK in one filter_complex pass.
    total_seconds = sum(shot.duration_seconds for shot in package.shots)
    inputs = ["-i", concat_path]
    filters: list[str] = []
    mix_labels = ["[0:a]"]

    for n, (narr_path, delay_ms) in enumerate(narrations, start=1):
        inputs += ["-i", narr_path]
        filters.append(f"[{n}:a]adelay={delay_ms}|{delay_ms}[narr{n}]")
        mix_labels.append(f"[narr{n}]")

    if bgm_path is not None:
        bgm_index = 1 + len(narrations)
        inputs += ["-i", bgm_path]
        fade_start = max(total_seconds - _BGM_FADE_SECONDS, 0)
        filters.append(
            f"[{bgm_index}:a]volume={_BGM_VOLUME},"
            f"afade=t=out:st={fade_start}:d={_BGM_FADE_SECONDS}[bgm]"
        )
        mix_labels.append("[bgm]")

    filters.append(
        f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:"
        "duration=first:normalize=0[aout]"
    )

    if package.hook_text:
        hook = _escape_drawtext(package.hook_text)
        filters.append(
            # fontfile value must be single-quoted INSIDE the filter or ffmpeg's
            # parser splits on the Windows drive colon (verified 2026-07-05)
            f"[0:v]drawtext=fontfile='{_FONTFILE}':text='{hook}':"
            "fontsize=64:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=18:"
            "x=(w-text_w)/2:y=h*0.18:"
            f"enable='between(t,0,{_HOOK_SECONDS})'[vout]"
        )
        video_map = "[vout]"
    else:
        video_map = "0:v"

    run_ffmpeg([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", video_map, "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        str(out_file),
    ])
    return str(out_file)
