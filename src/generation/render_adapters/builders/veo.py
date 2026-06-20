"""Veo 3.1 prompt builder.

Concrete PromptBuilder for Google Veo 3.1 (cli_id ``veo3_1``). The builder does
NOT carry Veo's dialect rules itself — it reads them at runtime from a
``RenderRules`` instance (``rules.model(cli_id)["dialect"]`` + ``rules.global_constraints()``),
so config/render_rules.yaml stays the single source of truth. The builder's job
is plumbing: fold the yaml-sourced dialect + constraints into an LLM "brief" and
ask the injected LLM to write the Veo-native prose.

Both the LLM wrapper and the RenderRules view are injected so tests can mock the
LLM and assert the INPUT (the brief) rather than calling a real model.
"""

from pydantic import BaseModel, Field

from src.generation.render_adapters.builders.base import PromptBuilder
from src.generation.render_adapters.rules import RenderRules
from src.providers.llm.anthropic_llm import AnthropicLLM
from src.schemas.generation import Shot


class _RenderPrompt(BaseModel):
    """Structured wrapper so the LLM returns exactly one prose prompt string."""

    prompt: str = Field(description="The model-native render prompt prose.")


class VeoBuilder(PromptBuilder):
    """Builds Veo 3.1-dialect render prompts; dialect read from RenderRules, not hardcoded."""

    def __init__(self, llm: AnthropicLLM | None = None, rules: RenderRules | None = None):
        self.llm = llm or AnthropicLLM(model="claude-sonnet-4-6")
        self.rules = rules or RenderRules()

    def _dialect_lines(self, cli_id: str) -> str:
        """Flatten this model's yaml dialect block into newline-joined guidance.

        Reads ``rules.model(cli_id)["dialect"]`` — a mapping of named rule keys
        (style, light_rule, audio_rule, beats_vs_timestamps, ...) to their rule
        strings — and joins the values so the brief carries every dialect rule
        the yaml defines, with no rule duplicated in Python. Veo's dialect
        values are all flat strings, so ``str(v)`` renders each cleanly.
        """
        dialect = self.rules.model(cli_id)["dialect"]
        return "\n".join(str(v) for v in dialect.values())

    def build_still_prompt(self, shot: Shot, mood_anchor: str) -> str:
        """Build the opening-still IMAGE prompt; this is where mood_anchor belongs.

        The still is an image-model prompt, so it reads the yaml's `still_dialect`
        (directive-stack order, camera-kit, authentic-imperfection, composition
        traps) — NOT a video model's dialect. mood_anchor carries the palette /
        lighting / realism the whole video inherits from this frame.
        """
        still_rules = "\n".join(str(v) for v in self.rules.still_dialect().values())
        brief = (
            "Write an image prompt for the opening still of a short video.\n"
            f"Still-prompt rules:\n{still_rules}\n"
            f"Frozen opening frame to depict: {shot.start_keyframe}\n"
            f"Palette / lighting / realism / uncanny register: {mood_anchor}\n"
            f"Global constraints: {'; '.join(self.rules.global_constraints())}"
        )
        return self.llm.parse(brief, _RenderPrompt, max_tokens=600).prompt

    def build_motion_prompt(self, shot: Shot, model_cli_id: str) -> str:
        """Build the image-to-video motion prompt; motion-only, no mood_anchor.

        The input still already carries palette/style, so this brief deliberately
        omits mood and describes only motion, pacing, and audio — Veo's i2v rule.
        Dialect and constraints come from the yaml via RenderRules, not hardcoded.
        """
        brief = (
            "Write a Veo 3.1 image-to-video MOTION prompt. The still already holds "
            "the style — describe ONLY motion, camera, pacing, and audio.\n"
            f"Veo dialect rules:\n{self._dialect_lines(model_cli_id)}\n"
            f"Motion to animate over ~5s: {shot.motion}\n"
            f"Global constraints: {'; '.join(self.rules.global_constraints())}"
        )
        return self.llm.parse(brief, _RenderPrompt, max_tokens=600).prompt
