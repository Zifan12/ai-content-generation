"""
Tests for src/reference/harvester.py — every collaborator faked, no network,
no ffmpeg, no LLM. Free functions are patched at their call-time import
source (``src.reference.harvester.<name>`` — the monkeypatch-import gotcha),
LLM wrappers are fake objects injected via the constructor.
"""

import json
from pathlib import Path

import pytest

import src.reference.harvester as hv
from src.reference.frame_harvester import DownloadError
from src.reference.harvester import Harvester
from src.reference.schemas import (
    FrameScore,
    FrameVerdict,
    QueryPlan,
    VideoCandidate,
    VideoPick,
)
from src.monitor.schemas import (
    BeatRole,
    CharacterRef,
    ContentMode,
    ShotSize,
    StoryBeat,
    StoryPitch,
)


# --- fixtures ---------------------------------------------------------------


def _pitch(characters: list[CharacterRef]) -> StoryPitch:
    return StoryPitch(
        logline="Eve finally gets her rematch.",
        mode=ContentMode.wish,
        characters=characters,
        desired_moment="the rematch the trailer denied",
        beats=[
            StoryBeat(
                role=BeatRole.hook,
                visual_line="Eve draws her blade",
                narration_line=None,
                shot_size=ShotSize.wide,
                characters_in_frame=["Eve"],
            ),
            StoryBeat(
                role=BeatRole.turn,
                visual_line="the arena gate opens",
                narration_line=None,
                shot_size=ShotSize.medium,
                characters_in_frame=["Eve"],
            ),
            StoryBeat(
                role=BeatRole.payoff,
                visual_line="blades clash",
                narration_line=None,
                shot_size=ShotSize.close_up,
                characters_in_frame=["Eve"],
                hero_moment=True,
            ),
        ],
        hook_line="She waited two years for this.",
        why_it_lands="the fandom is begging for it",
        legal_flag=False,
    )


def _candidate(video_id: str) -> VideoCandidate:
    return VideoCandidate(
        video_id=video_id,
        url=f"https://youtube.com/watch?v={video_id}",
        title="Stellar Blade official trailer",
        channel="PlayStation",
        duration_seconds=120.0,
        view_count=1000,
        description="",
        transcript_excerpt=None,
    )


def _usable_verdict() -> FrameVerdict:
    return FrameVerdict(
        character_present=True,
        face_visibility="clear",
        text_or_watermark_overlap=False,
        angle="front",
        single_character=True,
        usable=True,
        reason="clean frontal",
    )


def _unusable_verdict() -> FrameVerdict:
    return FrameVerdict(
        character_present=False,
        face_visibility="none",
        text_or_watermark_overlap=False,
        angle="unknown",
        single_character=False,
        usable=False,
        reason="character never on screen",
    )


class FakePlanner:
    def plan(self, character, pitch, context_block):
        return QueryPlan(
            queries=[
                "stellar blade official trailer",
                "stellar blade gameplay",
                "stellar blade eve cutscene",
            ],
            target_description="Eve front-facing, clear",
        )


class FakePicker:
    def __init__(self, chosen_ids: list[str]):
        self._ids = chosen_ids

    def pick(self, candidates, target_description):
        return VideoPick(chosen_video_ids=self._ids, reason="official upload")


class FakeJudge:
    def __init__(self, verdict: FrameVerdict):
        self._verdict = verdict
        self.judged_paths: list[Path] = []

    def judge(self, frame_path, character, appearance_hint):
        self.judged_paths.append(frame_path)
        return self._verdict


def _config(tmp_path: Path) -> dict:
    return {
        "search_limit_per_query": 8,
        "shortlist_size": 5,
        "max_duration_seconds": 900,
        "download_resolution_cap": 1080,
        "sharpness_laplacian_min": 100.0,
        "phash_distance_min": 6,
        "luminance_min": 40,
        "max_judge_frames": 40,
        "top_k_min": 1,
        "top_k_max": 8,
        "cache_root": str(tmp_path / "reference_cache"),
    }


@pytest.fixture
def patched_pipeline(monkeypatch, tmp_path):
    """Patch every free function on the harvester module to an offline fake:
    search returns one candidate per query, enrichment is identity, download
    'succeeds', extraction writes two real PNG-named files (so the approved-
    dir copy works), prefilter passes them all through."""

    monkeypatch.setattr(hv, "search_youtube", lambda q, limit: [_candidate("vid1")])
    monkeypatch.setattr(hv, "enrich_candidate", lambda c: c)

    def fake_download(url, dest_dir, *, max_duration_seconds, resolution_cap):
        dest_dir.mkdir(parents=True, exist_ok=True)
        video = dest_dir / "video.mp4"
        video.write_bytes(b"fake")
        return video

    def fake_extract(video_path, out_dir, *, max_frames=200):
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i in range(2):
            frame = out_dir / f"frame_{i:04d}.png"
            frame.write_bytes(b"png")
            paths.append(frame)
        return paths

    def fake_prefilter(frame_paths, **kwargs):
        return [
            FrameScore(path=str(p), sharpness=float(500 - i))
            for i, p in enumerate(frame_paths)
        ]

    monkeypatch.setattr(hv, "download_video", fake_download)
    monkeypatch.setattr(hv, "extract_frames", fake_extract)
    monkeypatch.setattr(hv, "delete_video", lambda p: None)
    monkeypatch.setattr(hv, "prefilter", fake_prefilter)
    return tmp_path


def _harvester(tmp_path, *, picker_ids=None, judge_verdict=None) -> Harvester:
    return Harvester(
        planner=FakePlanner(),
        picker=FakePicker(picker_ids if picker_ids is not None else ["vid1"]),
        judge=FakeJudge(judge_verdict or _usable_verdict()),
        config=_config(tmp_path),
    )


# --- tests ------------------------------------------------------------------


def test_happy_path_writes_approved_frames_and_manifest(patched_pipeline):
    tmp_path = patched_pipeline
    harvester = _harvester(tmp_path)
    character = CharacterRef(name="Eve", ip_source="Stellar Blade")

    results = harvester.run(_pitch([character]), "", pitch_id=7)

    assert len(results) == 1
    result = results[0]
    assert result.status == "ok"
    assert result.approved_dir is not None
    approved = list(Path(result.approved_dir).glob("*.png"))
    assert len(approved) == 2
    assert "approved_candidates" in result.approved_dir
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest["eve"]["queries"] == [
        "stellar blade official trailer",
        "stellar blade gameplay",
        "stellar blade eve cutscene",
    ]
    assert manifest["eve"]["selected"]


def test_empty_search_yields_no_video_with_manifest(patched_pipeline, monkeypatch):
    tmp_path = patched_pipeline
    monkeypatch.setattr(hv, "search_youtube", lambda q, limit: [])
    harvester = _harvester(tmp_path)

    results = harvester.run(
        _pitch([CharacterRef(name="Eve", ip_source="Stellar Blade")]), "", pitch_id=7
    )

    result = results[0]
    assert result.status == "no_video"
    assert result.approved_dir is None
    assert Path(result.manifest_path).exists()


def test_hallucinated_picker_ids_dropped_then_no_video(patched_pipeline):
    tmp_path = patched_pipeline
    harvester = _harvester(tmp_path, picker_ids=["not_a_real_id"])

    results = harvester.run(
        _pitch([CharacterRef(name="Eve", ip_source="Stellar Blade")]), "", pitch_id=7
    )

    result = results[0]
    assert result.status == "no_video"
    assert "picker" in result.detail
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest["eve"]["picker_ids_dropped"] == ["not_a_real_id"]


def test_judge_rejects_all_yields_no_usable_frames(patched_pipeline):
    tmp_path = patched_pipeline
    harvester = _harvester(tmp_path, judge_verdict=_unusable_verdict())

    results = harvester.run(
        _pitch([CharacterRef(name="Eve", ip_source="Stellar Blade")]), "", pitch_id=7
    )

    result = results[0]
    assert result.status == "no_usable_frames"
    assert result.approved_dir is None
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest["eve"]["frames"]  # verdicts recorded even on rejection


def test_first_download_fails_second_pick_attempted(patched_pipeline, monkeypatch):
    tmp_path = patched_pipeline
    monkeypatch.setattr(
        hv,
        "search_youtube",
        lambda q, limit: [_candidate("vid1"), _candidate("vid2")],
    )
    attempts = []

    def failing_then_ok(url, dest_dir, *, max_duration_seconds, resolution_cap):
        attempts.append(url)
        if "vid1" in url:
            raise DownloadError("bot check")
        dest_dir.mkdir(parents=True, exist_ok=True)
        video = dest_dir / "video.mp4"
        video.write_bytes(b"fake")
        return video

    monkeypatch.setattr(hv, "download_video", failing_then_ok)
    harvester = _harvester(tmp_path, picker_ids=["vid1", "vid2"])

    results = harvester.run(
        _pitch([CharacterRef(name="Eve", ip_source="Stellar Blade")]), "", pitch_id=7
    )

    assert len(attempts) == 2
    result = results[0]
    assert result.status == "ok"
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert len(manifest["eve"]["download_errors"]) == 1


def test_all_downloads_fail_yields_no_video(patched_pipeline, monkeypatch):
    tmp_path = patched_pipeline

    def always_fails(url, dest_dir, *, max_duration_seconds, resolution_cap):
        raise DownloadError("region locked")

    monkeypatch.setattr(hv, "download_video", always_fails)
    harvester = _harvester(tmp_path)

    results = harvester.run(
        _pitch([CharacterRef(name="Eve", ip_source="Stellar Blade")]), "", pitch_id=7
    )

    assert results[0].status == "no_video"


def test_unexpected_exception_maps_to_error_with_manifest(
    patched_pipeline, monkeypatch
):
    tmp_path = patched_pipeline
    monkeypatch.setattr(
        hv,
        "search_youtube",
        lambda q, limit: (_ for _ in ()).throw(RuntimeError("yt-dlp exploded")),
    )
    harvester = _harvester(tmp_path)

    results = harvester.run(
        _pitch([CharacterRef(name="Eve", ip_source="Stellar Blade")]), "", pitch_id=7
    )

    result = results[0]
    assert result.status == "error"
    assert "yt-dlp exploded" in result.detail
    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert "yt-dlp exploded" in manifest["eve"]["error"]


def test_two_characters_two_results_separate_dirs(patched_pipeline):
    tmp_path = patched_pipeline
    harvester = _harvester(tmp_path)
    characters = [
        CharacterRef(name="Eve", ip_source="Stellar Blade"),
        CharacterRef(name="Lily", ip_source="Stellar Blade"),
    ]

    results = harvester.run(_pitch(characters), "", pitch_id=7)

    assert len(results) == 2
    dirs = {r.approved_dir for r in results}
    assert len(dirs) == 2
    assert all(r.status == "ok" for r in results)
    # Both sections merged into ONE per-pitch manifest.
    manifest = json.loads(Path(results[0].manifest_path).read_text(encoding="utf-8"))
    assert set(manifest) == {"eve", "lily"}


def test_needs_reference_false_skipped(patched_pipeline):
    tmp_path = patched_pipeline
    harvester = _harvester(tmp_path)
    characters = [
        CharacterRef(name="Eve", ip_source="Stellar Blade"),
        CharacterRef(name="Extra", ip_source="Stellar Blade", needs_reference=False),
    ]

    results = harvester.run(_pitch(characters), "", pitch_id=7)

    assert [r.character_name for r in results] == ["Eve"]
