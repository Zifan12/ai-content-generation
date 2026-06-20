import pytest

from src.generation.render_adapters.builders.base import PromptBuilder
from src.schemas.generation import Shot


def test_promptbuilder_abc():
    """The ABC enforces its contract: bare instantiation fails, a complete subclass works.

    PromptBuilder declares build_still_prompt and build_motion_prompt as
    abstract. Instantiating it directly must raise TypeError (Python refuses to
    build a class with unimplemented abstract methods). A subclass that fills in
    both methods instantiates fine — proving the contract is enforced, not just
    decorative.
    """
    with pytest.raises(TypeError):
        PromptBuilder()

    class StubBuilder(PromptBuilder):
        def build_still_prompt(self, shot: Shot, mood_anchor: str) -> str:
            return ""

        def build_motion_prompt(self, shot: Shot, model_cli_id: str) -> str:
            return ""

    builder = StubBuilder()
    assert isinstance(builder, PromptBuilder)
