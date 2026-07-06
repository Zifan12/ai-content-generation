"""
Harvest orchestrator (Task 11): wires planner -> search -> shortlist ->
picker -> download -> extract -> prefilter -> judge -> ranking per character,
writes the provenance manifest, and maps every failure mode to an explicit
``HarvestResult`` status.

Failure policy (spec table, fail-loud, never silent-empty):
- no candidates survive search/shortlist, the picker returns only
  hallucinated ids, or every picked download fails -> ``no_video``
- footage downloaded but no frame survives extraction/prefilter/judge/ranking
  -> ``no_usable_frames``
- any unexpected exception -> ``error`` with the exception in ``detail``,
  manifest still written
An empty approved folder can therefore only coexist with a non-``ok`` status.

Picker-id validation (standing review finding from the T1-6 review): the LLM
picker's ``chosen_video_ids`` are filtered against the actual shortlist ids
here, at the orchestration seam, so a hallucinated or prompt-injected id can
never reach ``download_video``.

Manifest: one ``manifest.json`` per pitch cache dir (spec §Manifest), keyed by
character name — each character's harvest merges its section in, so a partial
multi-character run still leaves earlier sections on disk. Records queries,
candidates + picker reason, per-frame verdicts + sharpness scores, the final
ranking, and the failure detail on non-ok paths. (LLM token actuals are a spec
line-item the current ``parse()`` wrappers don't expose; deferred with a note
rather than faked.)

Collaborators are injected (planner/picker/judge) or module-global functions
(search/enrich/shortlist/download/extract/prefilter/select_top) so tests fake
everything — patch ``src.reference.harvester.<name>``, the import source used
at call time.
"""

import json
import logging
import re
import shutil
from pathlib import Path

from src.monitor.schemas import CharacterRef, StoryPitch
from src.reference.frame_harvester import (
    DownloadError,
    delete_video,
    download_video,
    extract_frames,
    prefilter,
)
from src.reference.frame_judge import FrameJudge
from src.reference.query_planner import QueryPlanner
from src.reference.ranking import select_top
from src.reference.schemas import FrameScore, HarvestResult, VideoCandidate
from src.reference.video_finder import VideoPicker, shortlist
from src.reference.youtube_client import enrich_candidate, search_youtube

logger = logging.getLogger(__name__)


def _slug(name: str) -> str:
    """Filesystem-safe folder name for a character (lowercase, runs of
    non-alphanumerics collapsed to single underscores)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "character"


class Harvester:
    def __init__(
        self,
        planner: QueryPlanner,
        picker: VideoPicker,
        judge: FrameJudge,
        config: dict,
    ):
        """
        Args:
            planner: query planner (Task 4) — pitch context in, QueryPlan out.
            picker: LLM candidate picker (Task 6) — shortlist in, VideoPick out.
            judge: vision frame judge (Task 9) — frame + character in,
                FrameVerdict out.
            config: parsed ``config/reference_harvest.yaml`` dict; every
                tunable (search limits, duration cap, prefilter thresholds,
                judge cap, top-k) is read from here, never hardcoded (AUD-M21).
        """
        self.planner = planner
        self.picker = picker
        self.judge = judge
        self.config = config

    def run(
        self,
        pitch: StoryPitch,
        context_block: str,
        pitch_id: int,
    ) -> list[HarvestResult]:
        """
        Harvest reference frames for every ``needs_reference=True`` character
        in the pitch (spec grill Q6a: one full cycle per character, so judge
        verdicts stay per-identity).

        Returns one ``HarvestResult`` per harvested character, in pitch
        character order. A pitch with no needs_reference characters returns
        an empty list — the caller decides what that means.
        """
        cache_dir = Path(self.config["cache_root"]) / str(pitch_id)
        results = []
        for character in pitch.characters:
            if not character.needs_reference:
                continue
            results.append(
                self.run_for_character(character, pitch, context_block, cache_dir)
            )
        return results

    def run_for_character(
        self,
        character: CharacterRef,
        pitch: StoryPitch,
        context_block: str,
        cache_dir: Path,
    ) -> HarvestResult:
        """
        One full harvest cycle for one character: plan queries, search,
        shortlist, pick, download, extract, prefilter, judge, rank, and copy
        the selected frames to ``<cache_dir>/approved_candidates/<slug>/``
        for the human approval gate.

        Never raises: every failure mode maps to a ``HarvestResult`` status
        (see module docstring for the policy table), and the manifest section
        for this character is written on every path, including ``error``.
        """
        slug = _slug(character.name)
        manifest_path = cache_dir / "manifest.json"
        section: dict = {"character": character.model_dump()}
        try:
            return self._harvest(
                character, pitch, context_block, cache_dir, slug, section
            )
        except Exception as exc:  # fail-loud policy: error status, not a raise
            logger.exception("harvest failed for %s", character.name)
            section["error"] = f"{type(exc).__name__}: {exc}"
            self._write_manifest(manifest_path, slug, section)
            return HarvestResult(
                status="error",
                character_name=character.name,
                approved_dir=None,
                manifest_path=str(manifest_path),
                detail=f"unexpected {type(exc).__name__}: {exc}",
            )

    def _harvest(
        self,
        character: CharacterRef,
        pitch: StoryPitch,
        context_block: str,
        cache_dir: Path,
        slug: str,
        section: dict,
    ) -> HarvestResult:
        """The happy-path pipeline; early-returns a non-ok result at each
        failure seam. Called only from ``run_for_character``'s error guard."""
        manifest_path = cache_dir / "manifest.json"

        def _fail(status: str, detail: str) -> HarvestResult:
            section["failure_detail"] = detail
            self._write_manifest(manifest_path, slug, section)
            return HarvestResult(
                status=status,  # type: ignore[arg-type]
                character_name=character.name,
                approved_dir=None,
                manifest_path=str(manifest_path),
                detail=detail,
            )

        plan = self.planner.plan(character, pitch, context_block)
        section["queries"] = plan.queries
        section["target_description"] = plan.target_description

        candidates: list[VideoCandidate] = []
        for query in plan.queries:
            candidates.extend(
                search_youtube(query, self.config["search_limit_per_query"])
            )

        short = shortlist(
            candidates,
            ip_source=character.ip_source,
            max_duration_seconds=self.config["max_duration_seconds"],
            shortlist_size=self.config["shortlist_size"],
        )
        if not short:
            return _fail("no_video", "search produced no in-cap candidates")

        enriched = [enrich_candidate(c) for c in short]
        section["candidates"] = [c.model_dump() for c in enriched]

        pick = self.picker.pick(enriched, plan.target_description)
        section["picker_reason"] = pick.reason
        by_id = {c.video_id: c for c in enriched}
        # Standing-finding fix: only ids that exist in the shortlist may flow
        # to download — a hallucinated/injected id is dropped, loudly.
        valid_ids = [vid for vid in pick.chosen_video_ids if vid in by_id]
        dropped = [vid for vid in pick.chosen_video_ids if vid not in by_id]
        if dropped:
            logger.warning("picker returned unknown video ids, dropped: %s", dropped)
            section["picker_ids_dropped"] = dropped
        section["picker_ids"] = valid_ids
        if not valid_ids:
            return _fail("no_video", "picker returned no valid candidate ids")

        work_dir = cache_dir / slug
        frame_paths: list[Path] = []
        downloaded_urls: list[str] = []
        download_errors: list[str] = []
        for vid in valid_ids:
            candidate = by_id[vid]
            try:
                video_path = download_video(
                    candidate.url,
                    work_dir / "video",
                    max_duration_seconds=self.config["max_duration_seconds"],
                    resolution_cap=self.config["download_resolution_cap"],
                )
            except DownloadError as exc:
                # Spec: per-video download error -> skip to next pick, log.
                logger.warning("download failed for %s: %s", candidate.url, exc)
                download_errors.append(f"{candidate.url}: {exc}")
                continue
            frame_paths.extend(extract_frames(video_path, work_dir / "frames"))
            delete_video(video_path)
            downloaded_urls.append(candidate.url)
        section["downloaded_urls"] = downloaded_urls
        section["download_errors"] = download_errors
        if not downloaded_urls:
            return _fail("no_video", "every picked video failed to download")
        if not frame_paths:
            return _fail("no_usable_frames", "extraction produced no frames")

        prefiltered = prefilter(
            frame_paths,
            sharpness_min=self.config["sharpness_laplacian_min"],
            phash_distance_min=self.config["phash_distance_min"],
            luminance_min=self.config["luminance_min"],
            max_out=self.config["max_judge_frames"],
        )
        if not prefiltered:
            return _fail("no_usable_frames", "no frame survived the prefilter")

        # v1 passes no appearance hint: the context bundle is prose, not a
        # structured appearance field — the judge prompt degrades honestly
        # without one (spec grill Q1c).
        judged = [
            FrameScore(
                path=frame.path,
                sharpness=frame.sharpness,
                verdict=self.judge.judge(Path(frame.path), character, None),
            )
            for frame in prefiltered
        ]
        section["frames"] = [f.model_dump() for f in judged]

        selected = select_top(
            judged,
            k_min=self.config["top_k_min"],
            k_max=self.config["top_k_max"],
        )
        section["selected"] = [f.path for f in selected]
        if not selected:
            return _fail("no_usable_frames", "judge passed no frame as usable")

        approved_dir = cache_dir / "approved_candidates" / slug
        approved_dir.mkdir(parents=True, exist_ok=True)
        for frame in selected:
            shutil.copy2(frame.path, approved_dir / Path(frame.path).name)

        shortfall = len(selected) < self.config["top_k_min"]
        detail = (
            f"{len(selected)} frames approved"
            + (f" (below top_k_min={self.config['top_k_min']})" if shortfall else "")
        )
        self._write_manifest(manifest_path, slug, section)
        return HarvestResult(
            status="ok",
            character_name=character.name,
            approved_dir=str(approved_dir),
            manifest_path=str(manifest_path),
            detail=detail,
        )

    @staticmethod
    def _write_manifest(manifest_path: Path, slug: str, section: dict) -> None:
        """Merge this character's section into the per-pitch manifest, keyed
        by slug — written on EVERY exit path so failures leave provenance."""
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest: dict = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("manifest unreadable, rewriting: %s", manifest_path)
        manifest[slug] = section
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
