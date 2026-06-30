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

    def fake_run_cli(argv: list[str]) -> str:
        recorded.append(argv)
        if "create" in argv:
            raise AssertionError("execute must not call create in dry_run")
        return "3.0"

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
