"""Tests for the v3 multi-group executor (plan 2026-07-04 Task 6).

Fake CLI / download / probe throughout — zero credits, no network. Pins:
cost-preflight-before-any-create, dry_run spends nothing, group loop wires each
still into the following video job via --start-image, still jobs carry repeated
--image-references, per-model extra flags, the audio warning, and the resume
manifest (a crash mid-run re-renders only the unfinished jobs).
"""

import subprocess

import pytest

from src.generation.executor import PackageRenderResult, execute, execute_scene
from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob


def _jobs() -> list[RenderJob]:
    """Adapter-shaped list: kling group (shots 0-2) + veo breakout (shot 3)."""
    return [
        RenderJob(
            model_cli_id="nano_banana_2", kind="still", prompt="group still",
            aspect_ratio="9:16", shot_index=0,
            reference_images=["refs/a.jpg", "refs/b.jpg"],
        ),
        RenderJob(
            model_cli_id="kling3_0", kind="multi_shot", prompt="Shot 1 (0-4s): x",
            aspect_ratio="9:16", shot_index=0, duration=12, covers_shots=[0, 1, 2],
        ),
        RenderJob(
            model_cli_id="nano_banana_2", kind="still", prompt="breakout still",
            aspect_ratio="9:16", shot_index=3,
            reference_images=["refs/a.jpg", "refs/b.jpg"],
        ),
        RenderJob(
            model_cli_id="veo3_1", kind="motion", prompt="water arcs. Audio: spray.",
            aspect_ratio="9:16", shot_index=3, duration=6,
        ),
    ]


class FakeCLI:
    """Records argv calls; answers cost with 5cr and create with a unique URL."""

    def __init__(self, fail_on_create_number: int | None = None):
        self.calls: list[list[str]] = []
        self._creates = 0
        self._fail_on = fail_on_create_number

    def __call__(self, argv):
        self.calls.append(argv)
        if argv[2] == "cost":
            return "5 credits"
        self._creates += 1
        if self._fail_on is not None and self._creates == self._fail_on:
            raise subprocess.CalledProcessError(1, argv)
        return f"https://cdn.example/{argv[3]}_{self._creates}.mp4"

    @property
    def create_calls(self):
        return [c for c in self.calls if c[2] == "create"]


def _fake_download(url, dest):
    with open(dest, "w") as f:
        f.write(url)
    return dest


@pytest.fixture(scope="module")
def rules():
    return RenderRules()


def test_dry_run_estimates_everything_and_creates_nothing(tmp_path, capsys, rules):
    cli = FakeCLI()
    result = execute(_jobs(), str(tmp_path), dry_run=True, run_cli=cli, rules=rules)
    assert result.credits_spent == 20.0  # 4 jobs x 5cr
    assert result.still_paths == [] and result.clips == [] and result.manifest_path == ""
    assert cli.create_calls == []
    out = capsys.readouterr().out
    assert "Estimated total: 20.0 credits" in out
    assert out.count("cr") >= 4  # per-job lines printed


def test_cost_preflight_runs_before_any_create(tmp_path, rules):
    cli = FakeCLI()
    execute(
        _jobs(), str(tmp_path),
        run_cli=cli, download=_fake_download, probe_audio=lambda p: True, rules=rules,
    )
    kinds = [c[2] for c in cli.calls]
    first_create = kinds.index("create")
    assert all(k == "cost" for k in kinds[:first_create])
    assert kinds[:first_create].count("cost") == 4


def test_group_loop_wires_stills_refs_and_flags(tmp_path, rules):
    cli = FakeCLI()
    result = execute(
        _jobs(), str(tmp_path),
        run_cli=cli, download=_fake_download, probe_audio=lambda p: True, rules=rules,
    )
    creates = cli.create_calls
    assert [c[3] for c in creates] == ["nano_banana_2", "kling3_0", "nano_banana_2", "veo3_1"]

    # stills carry repeated --image-references, never --start-image
    for still_call in (creates[0], creates[2]):
        assert still_call.count("--image-references") == 2
        assert "--start-image" not in still_call

    # each video job is seeded by ITS group's still (the one just rendered)
    kling_call, veo_call = creates[1], creates[3]
    assert kling_call[kling_call.index("--start-image") + 1] == result.still_paths[0]
    assert veo_call[veo_call.index("--start-image") + 1] == result.still_paths[1]

    # per-model extras: veo gets --quality high, kling does not
    assert "--quality" in veo_call and "--quality" not in kling_call

    # clips map to their covered shots
    assert [clip.shot_indices for clip in result.clips] == [[0, 1, 2], [3]]
    assert isinstance(result, PackageRenderResult)


def test_manifest_resume_skips_completed_jobs(tmp_path, rules):
    # First run dies on the 3rd create (the breakout still).
    dying = FakeCLI(fail_on_create_number=3)
    with pytest.raises(subprocess.CalledProcessError):
        execute(
            _jobs(), str(tmp_path),
            run_cli=dying, download=_fake_download,
            probe_audio=lambda p: True, rules=rules,
        )
    assert len(dying.create_calls) == 3  # two completed + the fatal third

    # Second run must skip the two completed jobs and finish the rest.
    resumed = FakeCLI()
    result = execute(
        _jobs(), str(tmp_path),
        run_cli=resumed, download=_fake_download,
        probe_audio=lambda p: True, rules=rules,
    )
    assert [c[3] for c in resumed.create_calls] == ["nano_banana_2", "veo3_1"]
    assert len(result.clips) == 2  # full result despite partial re-render
    assert result.manifest_path.endswith("render_manifest.json")


def test_silent_clip_on_audio_model_warns(tmp_path, capsys, rules):
    execute(
        _jobs(), str(tmp_path),
        run_cli=FakeCLI(), download=_fake_download,
        probe_audio=lambda p: False, rules=rules,
    )
    out = capsys.readouterr().out
    assert "WARNING" in out and "kling3_0" in out and "veo3_1" in out


# --- SCENE LANE (execute_scene, plan 2026-07-06 Task 5) ---------------------------


def _scene_job() -> RenderJob:
    return RenderJob(
        model_cli_id="seedance_2_0", kind="multi_shot",
        prompt="scene prose. Then cut to: more prose. No music.",
        aspect_ratio="9:16", shot_index=0, duration=10,
        reference_images=["refs/eve/front.png", "refs/eve/profile.png"],
        covers_shots=[0, 1, 2],
    )


def test_scene_dry_run_estimates_from_yaml_and_never_calls_cli(tmp_path, rules):
    cli = FakeCLI()
    result = execute_scene(
        _scene_job(), str(tmp_path), takes=2, dry_run=True, run_cli=cli, rules=rules
    )
    # billing-verified 4.5cr/s at 720p x 10s x 2 takes — no CLI cost calls at all
    assert result.credits_spent == 90.0
    assert cli.calls == []
    assert result.clips == []


def test_scene_takes_n_means_n_submissions_with_refs_and_params(tmp_path, rules):
    cli = FakeCLI()
    result = execute_scene(
        _scene_job(), str(tmp_path), takes=3,
        run_cli=cli, download=_fake_download, probe_audio=lambda p: True, rules=rules,
    )
    assert len(cli.create_calls) == 3
    argv = cli.create_calls[0]
    assert argv[3] == "seedance_2_0"
    assert argv.count("--image") == 2  # repeated per ref (spec A4)
    assert argv[argv.index("--duration") + 1] == "10"
    assert argv[argv.index("--resolution") + 1] == "720p"
    assert argv[-1] == "--wait"
    assert [c.clip_path.endswith(f"take_{k}.mp4") for k, c in enumerate(result.clips, 1)] == [True] * 3
    assert all(c.shot_indices == [0, 1, 2] for c in result.clips)


def test_scene_failed_take_reports_and_continues(tmp_path, capsys, rules):
    cli = FakeCLI(fail_on_create_number=2)
    result = execute_scene(
        _scene_job(), str(tmp_path), takes=3,
        run_cli=cli, download=_fake_download, probe_audio=lambda p: True, rules=rules,
    )
    out = capsys.readouterr().out
    assert len(cli.create_calls) == 3  # take 2 failed, take 3 still submitted
    assert len(result.clips) == 2
    assert "take 2/3 FAILED (uncharged)" in out
    assert "1/3 takes failed" in out


def test_scene_manifest_resume_skips_completed_takes(tmp_path, rules):
    first = FakeCLI()
    execute_scene(
        _scene_job(), str(tmp_path), takes=2,
        run_cli=first, download=_fake_download, probe_audio=lambda p: True, rules=rules,
    )
    second = FakeCLI()
    result = execute_scene(
        _scene_job(), str(tmp_path), takes=2,
        run_cli=second, download=_fake_download, probe_audio=lambda p: True, rules=rules,
    )
    assert second.create_calls == []  # both takes resumed from the manifest
    assert len(result.clips) == 2


def test_scene_resolution_override_walks_the_ladder(tmp_path, capsys, rules):
    cli = FakeCLI()
    result = execute_scene(
        _scene_job(), str(tmp_path), takes=1, resolution="480p", dry_run=True,
        run_cli=cli, rules=rules,
    )
    out = capsys.readouterr().out
    # 480p has no measured rate yet -> falls back to the 720p rate, loudly
    assert "no measured credit rate for 480p" in out
    assert result.credits_spent == 45.0
