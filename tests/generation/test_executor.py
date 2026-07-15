"""Tests for the scene-lane executor (plan 2026-07-06 Task 5; legacy group
executor deleted Task 10).

Fake CLI / download / probe throughout — zero credits, no network. Pins:
dry-run-zero-CLI yaml-rate estimates, N takes = N submissions with refs and
params, failed-take-continues, per-take resume manifest, ladder fallback note.
"""

import subprocess

import pytest

from src.generation.executor import execute_scene, execute_splice
from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob


class FakeCLI:
    """Records argv calls; answers create with a unique URL, optionally failing
    the Nth create to exercise the failed-take path."""

    def __init__(self, fail_on_create_number: int | None = None):
        self.calls: list[list[str]] = []
        self._creates = 0
        self._fail_on = fail_on_create_number

    def __call__(self, argv):
        self.calls.append(argv)
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


# --- PER-SCENE SPLICE LANE (execute_splice, Way 2, 2026-07-14 grill) --------------
# N DIFFERENT jobs rendered once each (vs execute_scene's N takes of ONE job).
# Decisions confirmed with the user 2026-07-14: one generation per shot (no retake
# ladder in v1), and ANY shot failing aborts the whole render (no holed video).


def _scene_shot_jobs(count: int = 3) -> list[RenderJob]:
    """One scene_shot job per shot, as adapter._shot_jobs would emit them."""
    return [
        RenderJob(
            model_cli_id="seedance_2_0", kind="scene_shot",
            prompt=f"shot {i} prose. Audio: rain. No music.",
            aspect_ratio="9:16", shot_index=i, duration=7,
            reference_images=["refs/eve/front.png"],
            covers_shots=[i],
        )
        for i in range(count)
    ]


def test_splice_renders_one_generation_per_job(tmp_path, rules):
    cli = FakeCLI()
    result = execute_splice(
        _scene_shot_jobs(), str(tmp_path),
        run_cli=cli, download=_fake_download, probe_audio=lambda p: True, rules=rules,
    )
    assert len(cli.create_calls) == 3  # one per shot, NOT takes of one job
    assert [c.shot_indices for c in result.clips] == [[0], [1], [2]]
    assert [c.clip_path.endswith(f"scene_shot_{i}.mp4") for i, c in enumerate(result.clips)] == [True] * 3
    argv = cli.create_calls[0]
    # duration rides the job (splice_defaults 7s), not the 15s single_gen default
    assert argv[argv.index("--duration") + 1] == "7"
    assert argv[argv.index("--resolution") + 1] == "720p"
    assert argv[-1] == "--wait"


def test_splice_dry_run_estimates_from_yaml_and_never_calls_cli(tmp_path, rules):
    cli = FakeCLI()
    result = execute_splice(
        _scene_shot_jobs(), str(tmp_path), dry_run=True, run_cli=cli, rules=rules,
    )
    # billing-verified 4.5cr/s @720p x 7s x 3 shots — the whole point of the
    # preflight is that this number is known before anything is spent (ADR-0007)
    assert result.credits_spent == 94.5
    assert cli.calls == []
    assert result.clips == []


def test_splice_aborts_on_shot_failure(tmp_path, rules):
    """A failed shot stops the render dead — no partial, holed video (user
    decision 2026-07-14; failed jobs are uncharged, FINDINGS.md)."""
    cli = FakeCLI(fail_on_create_number=2)
    with pytest.raises(subprocess.CalledProcessError):
        execute_splice(
            _scene_shot_jobs(), str(tmp_path),
            run_cli=cli, download=_fake_download, probe_audio=lambda p: True, rules=rules,
        )
    assert len(cli.create_calls) == 2  # shot 2 never submitted


def test_splice_manifest_resumes_completed_shots_after_abort(tmp_path, rules):
    """What makes abort-on-failure cheap: the shots that DID land are in the
    manifest, so the re-run re-renders only the one that failed."""
    first = FakeCLI(fail_on_create_number=3)
    with pytest.raises(subprocess.CalledProcessError):
        execute_splice(
            _scene_shot_jobs(), str(tmp_path),
            run_cli=first, download=_fake_download, probe_audio=lambda p: True, rules=rules,
        )
    second = FakeCLI()
    result = execute_splice(
        _scene_shot_jobs(), str(tmp_path),
        run_cli=second, download=_fake_download, probe_audio=lambda p: True, rules=rules,
    )
    assert len(second.create_calls) == 1  # shots 0-1 resumed, only shot 2 re-rendered
    assert len(result.clips) == 3
    assert [c.shot_indices for c in result.clips] == [[0], [1], [2]]


def test_splice_warns_when_audio_model_returns_mute_clip(tmp_path, capsys, rules):
    cli = FakeCLI()
    execute_splice(
        _scene_shot_jobs(1), str(tmp_path),
        run_cli=cli, download=_fake_download, probe_audio=lambda p: False, rules=rules,
    )
    assert "should emit native audio" in capsys.readouterr().out
