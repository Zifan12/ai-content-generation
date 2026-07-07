"""Render executor v3: run a multi-shot package's RenderJobs on the Higgsfield CLI.

Consumes the adapter's ordered job list — [group0 still, group0 video, group1
still, group1 video, ...] — and executes it group by group:

    still create (--image-references <key-art> ...)  ->  download still
    ->  video create (--start-image <that still>)     ->  download clip
    ->  ffprobe the clip for an audio stream

Cost preflight ALWAYS runs first: every job is estimated (``generate cost``),
printed per-job and totaled, before any paid create call (DECISIONS_LOCKED L7).
``dry_run`` returns right after the estimate.

RESUME MANIFEST (D14): every completed job is recorded in
``<out_dir>/render_manifest.json`` keyed by ``kind:shot_index``, with its result
URL and local path, written AFTER the download lands. A re-run over the same
out_dir skips completed jobs — a crash on shot 4 of 5 re-renders only 4 and 5,
never re-spending the finished shots. (OpenMontage's completed-ids checkpoint
shape, enforced in code rather than agent convention.)

All side-effecting boundaries — the CLI, downloads, the ffprobe audio probe —
are injected as callables (defaulting to real implementations) so tests drive
the whole flow with zero credits and no network/subprocess.

CLI-interface caveats (verified against CLI 1.1.5 param tables, 2026-07-04):
  * i2v seed flag is ``--start-image <path-or-id>`` on kling3_0 AND veo3_1 (the
    0.2.3-era ``--image`` is gone). Local PATHS are passed directly per the
    helptext; Kling path-feeding is render-proven (2026-07-04 spike). If veo3_1
    rejects a bare path on its first real run, add an ``upload create`` branch.
  * nano_banana_2 references: repeated ``--image-references``, max 14.
  * ``--quality high`` exists on veo3_1 only (kling uses ``mode``, default std) —
    extra flags are per-model via _VIDEO_EXTRA_FLAGS.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob

MANIFEST_NAME = "render_manifest.json"

# Model-specific extra flags for video create calls. veo3_1's quality param
# defaults to "basic"; we render high (the established single-shot default).
_VIDEO_EXTRA_FLAGS: dict[str, list[str]] = {
    "veo3_1": ["--quality", "high"],
}


class ShotClip(BaseModel):
    """One rendered clip and the package shot indices it covers.

    A singleton motion job covers one index; a multi_shot job covers its whole
    consistency group. ``has_audio`` is the ffprobe result for this clip.
    """

    shot_indices: list[int]
    clip_path: str
    has_audio: bool


class PackageRenderResult(BaseModel):
    """Outcome of executing one package's render jobs.

    Attributes:
        still_paths: Downloaded seed stills, in group order ([] in dry_run).
        clips: Downloaded clips with their covered shot indices, in group order
            ([] in dry_run).
        credits_spent: Summed pre-call credit estimate across all jobs (the cost
            command's figure, not a post-hoc bill). The only meaningful field in
            dry_run.
        manifest_path: Path of the resume manifest ("" in dry_run).
    """

    still_paths: list[str]
    clips: list[ShotClip]
    credits_spent: float
    manifest_path: str


def _run_cli(argv: list[str]) -> str:
    """Run a higgsfield CLI command and return its stdout.

    The executable is resolved once via ``shutil.which`` — on Windows this
    finds the npm-installed .cmd shim through PATHEXT, so no ``shell=True`` is
    needed and cmd.exe never receives the argv as a raw command line to parse
    (audit AUD-C1). Prompt text is additionally sanitized in ``_sanitize_prompt``
    because CreateProcess still routes .cmd files through cmd.exe internally,
    whose parser is not reliably escapable.

    Raises:
        FileNotFoundError: if the higgsfield CLI is not on PATH.
        subprocess.CalledProcessError: if the CLI exits non-zero.
    """
    executable = shutil.which(argv[0])
    if executable is None:
        raise FileNotFoundError(
            f"{argv[0]!r} CLI not found on PATH — is the npm package installed?"
        )
    completed = subprocess.run(
        [executable, *argv[1:]],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def _sanitize_prompt(text: str) -> str:
    """Strip cmd.exe metacharacters from prompt text before it enters argv.

    The Higgsfield CLI on Windows is an npm .cmd shim; CreateProcess executes
    .cmd files through cmd.exe even with shell=False, and cmd's argument
    parser is not reliably escapable (the "BatBadBut" class of injections).
    Prompts are prose — replacing quotes with apostrophes and dropping the
    handful of shell-hostile characters loses nothing a render model needs.
    Newlines collapse to spaces; the space-joined multi-shot prompt form is
    render-proven (2026-07-04 spike attempt 2 cut correctly from one line).
    """
    cleaned = text.replace('"', "'")
    cleaned = re.sub(r"[&|<>^%]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _download(url: str, dest: str) -> str:
    """Download ``url`` to ``dest`` and return ``dest``.

    Follows redirects (Higgsfield result URLs are presigned/redirected). The
    caller chooses the extension on ``dest``.
    """
    with httpx.stream("GET", url, follow_redirects=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    return dest


def _probe_audio(path: str) -> bool:
    """Return True if the media file at ``path`` has at least one audio stream.

    Uses ffprobe to list audio-stream codec types; a non-empty result means an
    audio track is present. ffprobe failing (missing binary, unreadable file)
    is treated as "no detectable audio" rather than crashing the run.
    """
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                path,
            ],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return "audio" in out


def _parse_credits(output: str) -> float:
    """Extract the credit figure from a ``generate cost`` stdout string.

    Pulls the first number (int or decimal) out of the output. Raises if no
    number is present, so a malformed cost output fails loud rather than
    silently summing to zero.
    """
    match = re.search(r"\d+(?:\.\d+)?", output)
    if match is None:
        raise ValueError(f"Could not parse a credit figure from cost output: {output!r}")
    return float(match.group())


def _extract_url(output: str) -> str:
    """Pull the first http(s) URL out of a ``generate create --wait`` stdout."""
    match = re.search(r"https?://\S+", output)
    if match is None:
        raise ValueError(f"No result URL found in create output: {output!r}")
    return match.group().rstrip(".,)\"'")


def _param_flags(job: RenderJob) -> list[str]:
    """The non-media param flags shared by a job's cost and create calls.

    Prompt + aspect ratio always; duration only for video jobs (stills have
    none). Media flags (--image-references / --start-image) and per-model
    extras are added by the create builder, not here, so the cost call
    estimates the same base shape without them.
    """
    flags = ["--prompt", _sanitize_prompt(job.prompt), "--aspect_ratio", job.aspect_ratio]
    if job.duration is not None:
        flags += ["--duration", str(job.duration)]
    return flags


def _cost_argv(job: RenderJob) -> list[str]:
    """Build the ``higgsfield generate cost <model> ...`` argv for a job."""
    return ["higgsfield", "generate", "cost", job.model_cli_id, *_param_flags(job)]


def _create_argv(job: RenderJob, start_image: str | None) -> list[str]:
    """Build the ``higgsfield generate create <model> ... --wait`` argv.

    Still jobs attach their grounding key-art via repeated --image-references
    (CLI 1.1.5, max 14). Video jobs are seeded with their group's rendered
    still via --start-image, plus any per-model extra flags.
    """
    argv = ["higgsfield", "generate", "create", job.model_cli_id, *_param_flags(job)]
    if job.kind == "still":
        for ref in job.reference_images:
            argv += ["--image-references", ref]
    else:
        if start_image is not None:
            argv += ["--start-image", start_image]
        argv += _VIDEO_EXTRA_FLAGS.get(job.model_cli_id, [])
    argv.append("--wait")
    return argv


def _job_key(job: RenderJob) -> str:
    """Manifest key for a job — kind + first covered shot uniquely identifies it
    within one package's job list (one still + one video per group)."""
    return f"{job.kind}:{job.shot_index}"


def _load_manifest(path: Path) -> dict:
    """Read the resume manifest, or an empty dict when none exists yet."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_manifest(path: Path, manifest: dict) -> None:
    """Persist the manifest after each completed job (crash-safe resume point)."""
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _scene_create_argv(
    job: RenderJob, *, duration: int, resolution: str
) -> list[str]:
    """Build the scene generation's ``generate create`` argv (spec A4).

    Refs attach as repeated ``--image`` (the CLI's alias for
    ``--image-references`` on seedance_2_0, verified via ``model get``
    2026-07-06); duration/resolution are explicit params, never prompt text
    (D2). ``--wait`` blocks until the job resolves so failures surface as a
    non-zero exit (uncharged, FINDINGS.md).
    """
    argv = [
        "higgsfield", "generate", "create", job.model_cli_id,
        "--prompt", _sanitize_prompt(job.prompt),
        "--aspect_ratio", job.aspect_ratio,
        "--duration", str(duration),
        "--resolution", resolution,
    ]
    for ref in job.reference_images:
        argv += ["--image", ref]
    argv.append("--wait")
    return argv


def _scene_take_estimate(rules: RenderRules, model_id: str, duration: int, resolution: str) -> float:
    """Per-take credit estimate from the yaml's billing-verified per-second rates.

    Reads ``limits.cost_estimate_credits.per_second_<resolution>`` for the
    scene model (measured from ``higgsfield account transactions`` 2026-07-06 —
    billing beats the cost subcommand, which was never validated against real
    charges). A resolution without a measured rate falls back to the 720p rate
    with a printed caveat rather than blocking the run.
    """
    costs = rules.model(model_id)["limits"]["cost_estimate_credits"]
    key = f"per_second_{resolution}"
    if key in costs:
        rate = float(costs[key])
    else:
        rate = float(costs["per_second_720p"])
        print(
            f"NOTE: no measured credit rate for {resolution}; estimating at the "
            f"720p rate ({rate}cr/s) — update the yaml after the first {resolution} bill."
        )
    return rate * duration


def execute_scene(
    job: RenderJob,
    out_dir: str,
    *,
    takes: int = 1,
    duration: int | None = None,
    resolution: str | None = None,
    dry_run: bool = False,
    run_cli=_run_cli,
    download=_download,
    probe_audio=_probe_audio,
    rules: RenderRules | None = None,
) -> PackageRenderResult:
    """Render the scene lane's ONE multi_shot job, ``takes`` times (D6).

    RETAKE LADDER (D6, methodology/15 L288-298): 480p to sanity-test a
    brand-new prompt (cheapest possible failure) -> 720p default single take
    for dev iteration -> 1080p x 2-3 takes for finals, user picks the best.
    ``takes``/``resolution`` are the flags that walk the ladder; defaults come
    from the yaml ``scene_lane.defaults`` block.

    Cost preflight prints takes x per-take estimate BEFORE any paid call
    (ADR-0007 / L7), computed from the yaml's billing-verified per-second
    rates — dry_run therefore makes NO CLI calls at all and returns the
    estimate. A failed take (CLI non-zero = uncharged on Higgsfield,
    FINDINGS.md) is reported and the loop continues with the next take —
    never an automatic re-roll of the same take (D3: failures are a human
    call, re-roll vs reword per scene_lane.reroll_vs_reword).

    Completed takes land as ``take_<k>.mp4`` and are recorded in the resume
    manifest under ``scene_take_<k>``; a re-run over the same out_dir renders
    only the missing takes.

    Args:
        job: The adapter's composed multi_shot scene job.
        out_dir: Directory for downloads + the resume manifest.
        takes: How many independent generations to run (default 1).
        duration: Override seconds; defaults to the job's (yaml-capped) value.
        resolution: Override; defaults to yaml scene_lane.defaults.resolution.
        dry_run: Estimate-and-return; no CLI calls, nothing spent.
        run_cli / download / probe_audio: Injected side-effect boundaries.
        rules: Render rules; built from config when None.

    Returns:
        PackageRenderResult — clips holds one ShotClip per SUCCESSFUL take
        (all covering the same shot indices), credits_spent holds the
        preflight estimate for the takes actually submitted this run.
    """
    rules = rules or RenderRules()
    defaults = rules.data["scene_lane"]["defaults"]
    duration = duration if duration is not None else (job.duration or int(defaults["duration_seconds"]))
    resolution = resolution or str(defaults["resolution"])

    per_take = _scene_take_estimate(rules, job.model_cli_id, duration, resolution)
    print(
        f"Scene render estimate: {takes} take(s) x {per_take}cr "
        f"({duration}s/{resolution}) = {per_take * takes}cr"
    )
    if dry_run:
        return PackageRenderResult(
            still_paths=[], clips=[], credits_spent=per_take * takes, manifest_path=""
        )

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    manifest_path = out_path / MANIFEST_NAME
    manifest = _load_manifest(manifest_path)

    clips: list[ShotClip] = []
    failed: list[int] = []
    for take in range(1, takes + 1):
        key = f"scene_take_{take}"
        if key in manifest and manifest[key].get("status") == "completed":
            path = manifest[key]["path"]
            print(f"[resume] skipping completed {key} -> {path}")
        else:
            try:
                url = _extract_url(
                    run_cli(_scene_create_argv(job, duration=duration, resolution=resolution))
                )
            except subprocess.CalledProcessError as err:
                # Failed jobs are uncharged (FINDINGS.md). Report, keep going —
                # the human decides re-roll vs reword afterwards (D3/D6).
                failed.append(take)
                print(f"take {take}/{takes} FAILED (uncharged): {err}")
                continue
            path = download(url, str(out_path / f"take_{take}.mp4"))
            manifest[key] = {"status": "completed", "url": url, "path": path}
            _save_manifest(manifest_path, manifest)

        has_audio = probe_audio(path)
        if rules.emits_audio(job.model_cli_id) and not has_audio:
            print(
                f"WARNING: {job.model_cli_id} should emit native audio but take "
                f"{take} has no audio stream ({path})."
            )
        clips.append(
            ShotClip(
                shot_indices=job.covers_shots or [job.shot_index],
                clip_path=path,
                has_audio=has_audio,
            )
        )

    if failed:
        print(f"{len(failed)}/{takes} takes failed (uncharged): takes {failed}")

    return PackageRenderResult(
        still_paths=[],
        clips=clips,
        credits_spent=per_take * takes,
        manifest_path=str(manifest_path),
    )


def execute(
    jobs: list[RenderJob],
    out_dir: str,
    *,
    dry_run: bool = False,
    run_cli=_run_cli,
    download=_download,
    probe_audio=_probe_audio,
    rules: RenderRules | None = None,
) -> PackageRenderResult:
    """Run a package's render jobs group by group, or estimate cost under dry_run.

    Walks the adapter's ordered list: each ``still`` job renders and becomes the
    ``--start-image`` seed for the video job that follows it. Completed jobs are
    recorded in the resume manifest and skipped on re-runs over the same out_dir.

    Args:
        jobs: The adapter's output — alternating still / video jobs in group order.
        out_dir: Directory for downloads + the resume manifest (created if
            missing). Unused in dry_run.
        dry_run: When True, only run the per-job cost estimate, print the table,
            and return with nothing spent.
        run_cli: Injected CLI runner (argv -> stdout).
        download: Injected (url, dest) -> path downloader.
        probe_audio: Injected (path) -> bool audio prober.
        rules: Render rules for the emits_audio sanity check; built lazily from
            config when None (only needed on the real path).

    Returns:
        A PackageRenderResult (see class docstring for dry_run semantics).
    """
    # Cost first, always — per-job lines + total before any paid call (L7).
    credits_spent = 0.0
    print("Render cost estimate:")
    for job in jobs:
        job_credits = _parse_credits(run_cli(_cost_argv(job)))
        credits_spent += job_credits
        print(f"  {job.kind:<10} {job.model_cli_id:<15} {job_credits}cr")
    print(f"Estimated total: {credits_spent} credits")

    if dry_run:
        return PackageRenderResult(
            still_paths=[], clips=[], credits_spent=credits_spent, manifest_path=""
        )

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    manifest_path = out_path / MANIFEST_NAME
    manifest = _load_manifest(manifest_path)

    still_paths: list[str] = []
    clips: list[ShotClip] = []
    current_still: str | None = None
    rules = rules or RenderRules()

    for job in jobs:
        key = _job_key(job)
        if key in manifest and manifest[key].get("status") == "completed":
            path = manifest[key]["path"]
            print(f"[resume] skipping completed {key} -> {path}")
        else:
            url = _extract_url(run_cli(_create_argv(job, start_image=current_still)))
            if job.kind == "still":
                ext = Path(urlparse(url).path).suffix or ".png"
                dest = str(out_path / f"still_{job.shot_index}{ext}")
            else:
                dest = str(out_path / f"clip_{job.shot_index}.mp4")
            path = download(url, dest)
            manifest[key] = {"status": "completed", "url": url, "path": path}
            _save_manifest(manifest_path, manifest)

        if job.kind == "still":
            current_still = path
            still_paths.append(path)
        else:
            has_audio = probe_audio(path)
            if rules.emits_audio(job.model_cli_id) and not has_audio:
                print(
                    f"WARNING: {job.model_cli_id} should emit native audio but the "
                    f"rendered clip has no audio stream ({path})."
                )
            clips.append(
                ShotClip(
                    shot_indices=job.covers_shots or [job.shot_index],
                    clip_path=path,
                    has_audio=has_audio,
                )
            )

    return PackageRenderResult(
        still_paths=still_paths,
        clips=clips,
        credits_spent=credits_spent,
        manifest_path=str(manifest_path),
    )
