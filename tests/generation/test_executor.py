import pytest

from src.generation.executor import RenderResult, execute
from src.generation.render_adapters.schemas import RenderJob


@pytest.fixture
def jobs() -> list[RenderJob]:
    """Minimal still + motion pair for executor tests (values are intentionally fake)."""
    still = RenderJob(
        model_cli_id="nano_banana_2",
        kind="still",
        prompt="fake still prompt",
        aspect_ratio="9:16",
        shot_index=0,
        duration=None,
    )
    motion = RenderJob(
        model_cli_id="veo3_1",
        kind="motion",
        prompt="fake motion prompt with Audio: room tone",
        aspect_ratio="9:16",
        shot_index=0,
        duration=8,
    )
    return [still, motion]


def test_execute_dry_run(jobs, tmp_path):
    recorded: list[list[str]] = []

    # Distinct per-model costs so the assertion proves execute SUMS them, not
    # doubles one or returns a single job's cost (2.0 + 4.0 = 6.0 is reachable
    # ONLY by real summation; a flat 3.0+3.0 would also be reachable by "last
    # cost * 2" and would not catch a non-summing bug).
    costs = {"nano_banana_2": "2.0", "veo3_1": "4.0"}

    def fake_run_cli(argv: list[str]) -> str:
        recorded.append(argv)
        if "create" in argv:
            raise AssertionError("execute must not call create in dry_run")
        return costs[argv[3]]

    result = execute(jobs, str(tmp_path), dry_run=True, run_cli=fake_run_cli)

    assert isinstance(result, RenderResult)
    assert len(recorded) == 2
    for argv in recorded:
        assert "cost" in argv
        assert "create" not in argv
    assert recorded[0][3] == "nano_banana_2"
    assert recorded[1][3] == "veo3_1"
    assert result.credits_spent == 6.0
    assert result.still_path == ""
    assert result.clip_path == ""
    assert result.has_audio is False


def test_execute_real_path_wires_still_into_motion(jobs, tmp_path):
    recorded: list[list[str]] = []
    costs = {"nano_banana_2": "2.0", "veo3_1": "4.0"}

    def fake_run_cli(argv: list[str]) -> str:
        recorded.append(argv)
        if "cost" in argv:
            return costs[argv[3]]
        # create: return a model-specific result URL the executor must parse.
        if argv[3] == "nano_banana_2":
            return "Done: https://cdn.test/still.png"
        return "Done: https://cdn.test/clip.mp4"

    # download(url, dest) -> dest: the still's local path is the dest the executor
    # chose; that exact string must reappear as the motion job's --image arg.
    def fake_download(url: str, dest: str) -> str:
        return dest

    result = execute(
        jobs,
        str(tmp_path),
        run_cli=fake_run_cli,
        download=fake_download,
        probe_audio=lambda path: True,
    )

    # the wire: the still's downloaded path is fed to the motion create's --image.
    motion_create = next(
        a for a in recorded if "create" in a and a[3] == "veo3_1"
    )
    image_idx = motion_create.index("--image")
    assert motion_create[image_idx + 1] == result.still_path

    assert result.still_path == str(tmp_path / "still.png")
    assert result.clip_path == str(tmp_path / "clip.mp4")
    assert result.has_audio is True
    assert result.credits_spent == 6.0
