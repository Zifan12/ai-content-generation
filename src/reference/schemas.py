"""Schemas for the reference harvester (src/reference/).

Pipeline: LLM query planner -> yt-dlp search + LLM candidate picker
(transcript-informed) -> yt-dlp download + ffmpeg scene-guided frame
extraction -> heuristic prefilter -> vision-LLM frame judge -> angle-diverse
ranking -> filesystem approval gate + provenance manifest.

Spec: docs/superpowers/specs/2026-07-05-reference-harvester-design.md
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class QueryPlan(BaseModel):
    """Query planner output: search queries + a description of the render target."""

    model_config = ConfigDict(extra="forbid")

    queries: list[str] = Field(min_length=1, max_length=5)
    target_description: str


class VideoCandidate(BaseModel):
    """One YouTube search/enrichment result considered for reference footage."""

    model_config = ConfigDict(extra="forbid")

    video_id: str
    url: str
    title: str
    channel: str
    duration_seconds: float
    view_count: int | None
    description: str
    transcript_excerpt: str | None = None


class VideoPick(BaseModel):
    """Candidate picker output: which video(s) to download, and why."""

    model_config = ConfigDict(extra="forbid")

    chosen_video_ids: list[str] = Field(min_length=1, max_length=2)
    reason: str


class FrameVerdict(BaseModel):
    """Vision-LLM judge output for a single extracted frame (spec Sec:frame_judge)."""

    model_config = ConfigDict(extra="forbid")

    character_present: bool
    face_visibility: Literal["clear", "partial", "none"]
    text_or_watermark_overlap: bool
    angle: Literal["front", "three_quarter", "profile", "back", "unknown"]
    single_character: bool
    usable: bool
    reason: str


class FrameScore(BaseModel):
    """A prefiltered frame plus its (optional, not-yet-judged) verdict."""

    model_config = ConfigDict(extra="forbid")

    path: str
    sharpness: float
    verdict: FrameVerdict | None = None


HarvestStatus = Literal["ok", "no_video", "no_usable_frames", "error"]


class HarvestResult(BaseModel):
    """Outcome of harvesting reference frames for one character."""

    model_config = ConfigDict(extra="forbid")

    status: HarvestStatus
    character_name: str
    approved_dir: str | None
    manifest_path: str
    detail: str
