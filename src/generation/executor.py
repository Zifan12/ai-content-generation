"""Render executor: run a single-shot package's RenderJobs on the Higgsfield CLI.

This is the missing back end of the pipeline. The adapter produces two
RenderJobs (a nano_banana_2 still + an i2v motion clip on the package's chosen
model); this module actually runs them:

    still create  ->  download image  ->  motion create (--image <still>)
                  ->  download clip   ->  ffprobe for an audio stream

``dry_run`` short-circuits the whole thing to the cost estimator: it calls
``higgsfield generate cost`` per job, sums the credits, spends nothing, and
returns empty paths. The credit total is printed before any paid call, per the
project render rule.

All side-effecting boundaries — the CLI, the image/clip download, and the
ffprobe audio probe — are injected as callables (defaulting to real
implementations) so tests drive the whole flow with zero credits and no
network/subprocess.

CLI-interface caveats to verify with ``higgsfield model get`` BEFORE the first
real (paid) run — the mocked tests cannot catch these:
  * cost-output format: ``_parse_credits`` extracts the first number from
    stdout; confirm ``higgsfield generate cost`` prints a parseable figure.
  * motion seed flag: the i2v seed is passed as ``--image``; veo3_1 may instead
    want ``--start-image`` (the media-roles table lists start_image for veo3_1).
  * ``--quality high``: confirm veo3_1 accepts it, or it errors "Unknown params".
"""

import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob

# Default frame aspect for both jobs; the motion clip's length rides on the
# job's own (already-capped) duration.
ASPECT_RATIO = "9:16"


class RenderResult(BaseModel):
    """Outcome of executing one package's render jobs.

    Attributes:
        still_path: Local path to the downloaded opening still ("" in dry_run).
        clip_path: Local path to the downloaded motion clip ("" in dry_run).
        credits_spent: Summed credit estimate across the jobs. In dry_run this
            is the only meaningful field; in a real run it is the pre-call
            estimate (what the cost command reported), not a post-hoc bill.
        has_audio: Whether the rendered clip carries an audio stream (False in
            dry_run, where nothing is rendered or probed).
    """

    still_path: str
    clip_path: str
    credits_spent: float
    has_audio: bool


def _run_cli(argv: list[str]) -> str:
    """Run a higgsfield CLI command and return its stdout.

    Raises:
        subprocess.CalledProcessError: if the CLI exits non-zero.
    """
    completed = subprocess.run(argv, capture_output=True, text=True, check=True)
    return completed.stdout


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

    Pulls the first number (int or decimal) out of the output. Robust to either
    a bare "2.0" or wrapped text like "Estimated cost: 2 credits". Raises if no
    number is present, so a malformed cost output fails loud rather than
    silently summing to zero.
    """
    match = re.search(r"\d+(?:\.\d+)?", output)
    if match is None:
        raise ValueError(f"Could not parse a credit figure from cost output: {output!r}")
    return float(match.group())


def _extract_url(output: str) -> str:
    """Pull the first http(s) URL out of a ``generate create --wait`` stdout.

    The CLI prints the result media URL on success. Strips common trailing
    punctuation so a URL at the end of a sentence parses cleanly.
    """
    match = re.search(r"https?://\S+", output)
    if match is None:
        raise ValueError(f"No result URL found in create output: {output!r}")
    return match.group().rstrip(".,)\"'")


def _param_flags(job: RenderJob) -> list[str]:
    """The non-media param flags shared by a job's cost and create calls.

    Prompt + aspect ratio always; duration only for video jobs (stills have
    none). Media flags (--image) and --wait/--quality are added by the create
    builder, not here, so the cost call estimates the same shape without them.
    """
    flags = ["--prompt", job.prompt, "--aspect_ratio", job.aspect_ratio]
    if job.duration is not None:
        flags += ["--duration", str(job.duration)]
    return flags


def _cost_argv(job: RenderJob) -> list[str]:
    """Build the ``higgsfield generate cost <model> ...`` argv for a job."""
    return ["higgsfield", "generate", "cost", job.model_cli_id, *_param_flags(job)]


def _create_argv(job: RenderJob, image: str | None) -> list[str]:
    """Build the ``higgsfield generate create <model> ... --wait`` argv.

    ``image`` seeds an i2v motion job (passed as --image); None for the still.
    --quality high is sent for video jobs (the single-shot quality default).
    """
    argv = ["higgsfield", "generate", "create", job.model_cli_id, *_param_flags(job)]
    if image is not None:
        argv += ["--image", image]
    if job.kind == "motion":
        argv += ["--quality", "high"]
    argv.append("--wait")
    return argv


def execute(
    jobs: list[RenderJob],
    out_dir: str,
    *,
    dry_run: bool = False,
    run_cli=_run_cli,
    download=_download,
    probe_audio=_probe_audio,
    rules: RenderRules | None = None,
) -> RenderResult:
    """Run a package's render jobs, or estimate their cost under dry_run.

    Args:
        jobs: The adapter's output — expected to contain one "still" job and one
            "motion" job (in that execution order).
        out_dir: Directory to download the still and clip into (created if
            missing). Unused in dry_run.
        dry_run: When True, only call the cost estimator per job, sum the
            credits, and return empty paths with has_audio=False. No paid call.
        run_cli: Injected CLI runner (argv -> stdout). Defaults to real
            subprocess; tests pass a fake to avoid spending credits.
        download: Injected (url, dest) -> path downloader.
        probe_audio: Injected (path) -> bool audio prober.
        rules: Render rules for the emits_audio sanity-check; built lazily from
            config when None (only needed on the real path).

    Returns:
        A RenderResult: credits in dry_run; paths + has_audio in a real run.
    """
    # Cost first, always — the credit total is reported before any paid create
    # call (project render rule: no silent spends).
    credits_spent = sum(_parse_credits(run_cli(_cost_argv(job))) for job in jobs)
    print(f"Estimated render cost: {credits_spent} credits")

    if dry_run:
        return RenderResult(
            still_path="",
            clip_path="",
            credits_spent=credits_spent,
            has_audio=False,
        )

    Path(out_dir).mkdir(parents=True, exist_ok=True)

    still_job = next(j for j in jobs if j.kind == "still")
    motion_job = next(j for j in jobs if j.kind == "motion")

    # 1. Render the opening still, download it.
    still_url = _extract_url(run_cli(_create_argv(still_job, image=None)))
    still_ext = Path(urlparse(still_url).path).suffix or ".png"
    still_path = download(still_url, str(Path(out_dir) / f"still{still_ext}"))

    # 2. Render the motion clip seeded by that still (--image), download it.
    clip_url = _extract_url(run_cli(_create_argv(motion_job, image=still_path)))
    clip_path = download(clip_url, str(Path(out_dir) / "clip.mp4"))

    # 3. Probe the clip for audio; warn if the model should emit audio but didn't.
    has_audio = probe_audio(clip_path)
    rules = rules or RenderRules()
    if rules.emits_audio(motion_job.model_cli_id) and not has_audio:
        print(
            f"WARNING: {motion_job.model_cli_id} should emit native audio but the "
            f"rendered clip has no audio stream ({clip_path})."
        )

    return RenderResult(
        still_path=still_path,
        clip_path=clip_path,
        credits_spent=credits_spent,
        has_audio=has_audio,
    )
