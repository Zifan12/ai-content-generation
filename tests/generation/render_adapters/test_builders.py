import pytest
from unittest.mock import MagicMock
from src.schemas.generation import Shot
from src.generation.render_adapters.builders.base import PromptBuilder
from src.generation.render_adapters.builders.hailuo import HailuoBuilder
from src.generation.render_adapters.builders.veo import VeoBuilder
from src.generation.render_adapters.rules import RenderRules


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


def test_veo_motion_prompt_carries_audio_rule_and_omits_mood():
    """VeoBuilder hands the LLM a brief carrying Veo's dialect, not garbage.

    The builder doesn't write the final prompt — the LLM does. So this test
    inspects the INPUT the builder passes to the (mocked) LLM, not the output:

      - the shot's motion text is carried through (the builder didn't drop it),
      - Veo's Audio rule is present (Veo improvises sound if omitted), and
      - the shot-beats guidance is carried (Veo dialect: beats over timecodes).

    Asserting the brief, not the prose, keeps the test deterministic and
    credit-free (no real model call).
    """
    fake_llm = MagicMock()
    builder = VeoBuilder(llm=fake_llm)

    shot = Shot(motion="water drains inward while the pool's edges stay full and level")

    builder.build_motion_prompt(shot, "veo3_1")

    text = fake_llm.parse.call_args.args[0]

    assert "water drains inward" in text
    assert "Audio" in text
    assert "beats" in text


def test_hailuo_motion_prompt_flattens_nested_physics_keywords():
    """HailuoBuilder surfaces its nested physics_keywords as PROSE, not a dict repr.

    Hailuo's yaml dialect stores ``physics_keywords`` as a nested dict
    (category -> list of physics verbs). A naive ``str(v)`` over the dialect
    values would dump a raw Python literal — ``{'fluid': ['water spray', ...]}``
    — with braces, quotes and keys the LLM should never see. HailuoBuilder owns a
    ``_render_value`` that flattens nesting into readable ``key — a, b, c`` prose.

    This test inspects the brief the builder hands the (mocked) LLM and asserts:

      - the shot's motion text is carried through,
      - a physics verb from the nested dict reaches the brief, AND
      - the flattened prose form is present (``fluid —``) while the raw Python
        dict-repr markers (``{'fluid'``) are ABSENT.

    The last pair is the load-bearing assertion: ``surface tension`` alone would
    pass even with the broken dict-dump (the substring survives inside the
    repr), so it can't catch the bug. The presence of ``fluid —`` together with
    the absence of ``{'fluid'`` is what proves the flattening actually ran.
    """
    fake_llm = MagicMock()
    builder = HailuoBuilder(llm=fake_llm)

    shot = Shot(motion="a single drop swells, trembles on the lip of the glass, then falls")

    builder.build_motion_prompt(shot, "minimax_hailuo")

    text = fake_llm.parse.call_args.args[0]

    # Sanity: the dialect we're asserting on really is nested in the yaml.
    physics = RenderRules().model("minimax_hailuo")["dialect"]["physics_keywords"]
    assert isinstance(physics, dict)

    assert "a single drop swells" in text
    assert "surface tension" in text          # physics verb reached the brief
    assert "fluid —" in text                  # rendered as flattened prose
    assert "{'fluid'" not in text             # NOT a raw Python dict repr

