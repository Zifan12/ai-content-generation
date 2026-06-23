import pytest
from src.generation.content_writer import (
    ContentWriter,
)
from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.adapter import render_jobs
from src.generation.executor import execute
from src.schemas.generation import ContentPackage, Shot


@pytest.fixture
def rules():
    return RenderRules()


def _mock_package(
    *, model_cli_id: str = "WRONG", premise: str = "WRONG PREMISE"
) -> ContentPackage:
    """LLM-shaped package; write() must overwrite provenance fields."""
    return ContentPackage(
        shot=Shot(
            start_keyframe="Handheld phone POV, kitchen counter, glass mid-spill.",
            motion="Water freezes in place as it pours. Audio: sharp tap of ice forming.",
        ),
        model_cli_id=model_cli_id,
        premise=premise,
        mood_anchor="Cool daylight, desaturated phone footage, photoreal.",
        onscreen_text=["wait is this real??"],
        caption="I still don't know what I filmed.",
        hashtags=["surreal", "fyp"],
    )


class FakeLLM:
    def __init__(self, package: ContentPackage | None = None):
        self.last_prompt: str | None = None
        self.last_system: str | None = None
        self.last_max_tokens: int | None = None
        self._package = package or _mock_package()

    def parse(self, prompt, response_model, system=None, max_tokens=1024):
        self.last_prompt = prompt
        self.last_system = system
        self.last_max_tokens = max_tokens
        return self._package


def test_pipeline(rules, tmp_path):
    recorded = []

    def fake_run_cli(argv: list[str]) -> str:
        recorded.append(argv)
        if "create" in argv:
            raise AssertionError("execute must not call create in dry_run")
        return "3.0"

    writer = ContentWriter(llm=FakeLLM())
    package = writer.write("a premise", rules=rules, model_cli_id="veo3_1")
    jobs = render_jobs(package, rules)
    result = execute(jobs, str(tmp_path), dry_run=True, run_cli=fake_run_cli)

    assert package.premise == "a premise"
    assert result.credits_spent == 6.0
    assert result.still_path == ""
    assert result.clip_path == ""
    assert len(recorded) == 2
    assert recorded[0][3] == "nano_banana_2"
    assert recorded[1][3] == "veo3_1"
    assert len(jobs) == 2
    assert package.model_cli_id == "veo3_1"
    assert result.has_audio is False