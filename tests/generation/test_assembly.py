"""Tests for the assembly step (plan 2026-07-04 Task 8).

Two layers:
  - Command-construction unit tests with an injected fake ffmpeg runner + fake
    TTS: narration offsets in ms, BGM volume/fade only when a bgm file is given,
    drawtext only when hook_text is set, overrun warning.
  - One REAL-ffmpeg integration test (spec §7 Stage-3 criterion 5): tiny lavfi
    color+sine clips in, one mp4 out, ffprobe duration = Σ authored durations
    ±1s, ≥1 audio stream. Skipped automatically when ffmpeg is not on PATH.
"""

import shutil
import subprocess

import pytest

from src.generation.assembly import assemble
from src.generation.executor import PackageRenderResult, ShotClip
from src.monitor.schemas import BeatRole
from src.schemas.generation import MotionTag, MultiShotPackage, ShotSpec


def _package(narrations=("A line.", None, "Third line.")) -> MultiShotPackage:
    shots = [
        ShotSpec(
            beat_role=BeatRole.build,
            motion_tag=MotionTag.character_consistency,
            scene_line=f"motion {i}. Audio: rain.",
            duration_seconds=4,
            narration_line=narrations[i],
            characters_in_frame=["Eve"],
            model_cli_id="kling3_0",
        )
        for i in range(3)
    ]
    return MultiShotPackage(
        shots=shots,
        style_anchor="style",
        anchors_block="anchors",
        hook_text="the scene they cut",
        caption="c",
        hashtags=[],
        music_brief=None,
    )


def _result(tmp_path, n_clips=1) -> PackageRenderResult:
    clips = []
    for i in range(n_clips):
        p = tmp_path / f"clip_{i}.mp4"
        p.write_bytes(b"fake")
        clips.append(
            ShotClip(shot_indices=[0, 1, 2] if n_clips == 1 else [i],
                     clip_path=str(p), has_audio=True)
        )
    return PackageRenderResult(
        still_paths=[], clips=clips, credits_spent=0.0, manifest_path=""
    )


class FakeTTS:
    def __init__(self):
        self.lines = []

    def synthesize(self, text, out_path):
        self.lines.append(text)
        with open(out_path, "wb") as f:
            f.write(b"fake-audio")
        return out_path


class FakeFFmpeg:
    def __init__(self):
        self.commands: list[list[str]] = []

    def __call__(self, argv):
        self.commands.append(argv)
        # concat/normalize outputs must exist for later stages' inputs
        out = argv[-1]
        if out.endswith(".mp4"):
            with open(out, "wb") as f:
                f.write(b"fake-video")


def test_narration_offsets_bgm_and_hook_in_final_command(tmp_path):
    ff = FakeFFmpeg()
    tts = FakeTTS()
    bgm = tmp_path / "bgm.mp3"
    bgm.write_bytes(b"fake-bgm")

    out = assemble(
        _result(tmp_path), _package(), str(tmp_path / "final.mp4"),
        tts=tts, bgm_path=str(bgm), run_ffmpeg=ff, probe_duration=lambda p: 3.0,
    )

    assert out.endswith("final.mp4")
    assert tts.lines == ["A line.", "Third line."]  # silent shot 1 skipped

    final = ff.commands[-1]
    graph = final[final.index("-filter_complex") + 1]
    # narration delays: shot 0 at 0ms, shot 2 at 8000ms (4s + 4s authored)
    assert "adelay=0|0" in graph
    assert "adelay=8000|8000" in graph
    # BGM at 0.2 volume with a fade ending at total duration (12s)
    assert "volume=0.2" in graph
    assert "afade=t=out:st=9:d=3" in graph
    # hook card burned for the first 2.5s
    assert "drawtext" in graph and "between(t,0,2.5)" in graph
    # native audio + 2 narrations + bgm mixed
    assert "amix=inputs=4" in graph
    # D5 tail-fade on the FINAL mix (12s total - 0.5s), kills the ending-click
    assert "[amixed]afade=t=out:st=11.5:d=0.5[aout]" in graph


def test_no_hook_no_bgm_minimal_graph(tmp_path):
    ff = FakeFFmpeg()
    package = _package(narrations=(None, None, None))
    package = package.model_copy(update={"hook_text": None})

    assemble(
        _result(tmp_path), package, str(tmp_path / "final.mp4"),
        tts=FakeTTS(), run_ffmpeg=ff, probe_duration=lambda p: 0.0,
    )
    final = ff.commands[-1]
    graph = final[final.index("-filter_complex") + 1]
    assert "drawtext" not in graph
    assert "volume=" not in graph
    assert "amix=inputs=1" in graph  # native audio only
    assert "[amixed]afade=t=out" in graph  # D5 tail-fade applies even bare
    assert "0:v" in final  # un-drawn video mapped directly


def test_normalize_then_concat_then_mix_order(tmp_path):
    ff = FakeFFmpeg()
    result = _result(tmp_path, n_clips=2)
    package = _package()
    # two clips need a 2-group package shape; reuse 3-shot package, clips cover [0]+[1]
    assemble(
        result, package, str(tmp_path / "final.mp4"),
        tts=FakeTTS(), run_ffmpeg=ff, probe_duration=lambda p: 1.0,
    )
    # 2 normalize passes + 1 concat + 1 final mix = 4 ffmpeg invocations
    assert len(ff.commands) == 4
    assert "-f" in ff.commands[2] and "concat" in ff.commands[2]
    concat_list = (tmp_path / "_assembly" / "concat.txt").read_text()
    assert concat_list.index("norm_0") < concat_list.index("norm_1")


def test_narration_overrun_warns(tmp_path, capsys):
    assemble(
        _result(tmp_path), _package(), str(tmp_path / "final.mp4"),
        tts=FakeTTS(), run_ffmpeg=FakeFFmpeg(), probe_duration=lambda p: 9.9,
    )
    assert "WARNING" in capsys.readouterr().out


def test_empty_clips_raises(tmp_path):
    empty = PackageRenderResult(still_paths=[], clips=[], credits_spent=0, manifest_path="")
    with pytest.raises(ValueError, match="no clips"):
        assemble(
            empty, _package(), str(tmp_path / "final.mp4"),
            tts=FakeTTS(), run_ffmpeg=FakeFFmpeg(),
        )


# --- real-ffmpeg integration (spec §7 Stage-3 criterion 5) ------------------------


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_integration_real_ffmpeg_duration_and_audio(tmp_path):
    def _make_clip(path, seconds):
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=blue:s=540x960:d={seconds}",
                "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                "-shortest", str(path),
            ],
            capture_output=True, check=True,
        )

    clip_a, clip_b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _make_clip(clip_a, 8)   # covers shots 0+1 (4s + 4s)
    _make_clip(clip_b, 4)   # covers shot 2

    class SineTTS:
        def synthesize(self, text, out_path):
            wav = out_path.replace(".mp3", ".wav")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i",
                 "sine=frequency=880:duration=1", wav],
                capture_output=True, check=True,
            )
            return wav

    result = PackageRenderResult(
        still_paths=[],
        clips=[
            ShotClip(shot_indices=[0, 1], clip_path=str(clip_a), has_audio=True),
            ShotClip(shot_indices=[2], clip_path=str(clip_b), has_audio=True),
        ],
        credits_spent=0.0,
        manifest_path="",
    )

    out = assemble(result, _package(), str(tmp_path / "final.mp4"), tts=SineTTS())

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", out],
        capture_output=True, text=True, check=True,
    )
    assert abs(float(probe.stdout.strip()) - 12.0) <= 1.0

    streams = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", out],
        capture_output=True, text=True, check=True,
    )
    assert "audio" in streams.stdout
