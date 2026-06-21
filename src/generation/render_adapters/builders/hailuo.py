"""Minimax Hailuo 02 prompt builder.

Concrete PromptBuilder for Minimax Hailuo 02 (cli_id ``minimax_hailuo``). Like
VeoBuilder, the dialect rules live in config/render_rules.yaml, not in Python —
the builder reads ``rules.model("minimax_hailuo")["dialect"]`` +
``rules.global_constraints(kind, style)`` at runtime and folds them into an LLM "brief".

Hailuo's dialect differs from Veo's in shape, not just content: its
``physics_keywords`` value is a NESTED dict (category -> list of physics verbs,
e.g. ``fluid: [water spray, fluid dynamics, surface tension]``), where Veo's
dialect values are all flat strings. A naive ``str(v)`` would dump a raw Python
dict repr (``{'fluid': ['water spray', ...]}``) into the brief — braces, quotes
and keys the LLM should not see. So this builder owns its OWN ``_dialect_lines``
that renders any nested value as readable prose. Hailuo wants a restrained
director's SCRIPT led by physical verbs (it drowns in piled-up adjectives), so
surfacing those verbs cleanly is the whole point.

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


class HailuoBuilder(PromptBuilder):
    """Builds Minimax Hailuo 02-dialect render prompts; dialect read from RenderRules."""

    def __init__(self, llm: AnthropicLLM | None = None, rules: RenderRules | None = None):
        self.llm = llm or AnthropicLLM(model="claude-sonnet-4-6")
        self.rules = rules or RenderRules()

    @staticmethod
    def _render_value(value: object) -> str:
        """Render one dialect value as readable prose, flattening nested structures.

        Flat strings pass through unchanged. A list becomes a comma-joined run
        (``water spray, fluid dynamics, surface tension``). A dict becomes
        ``key — <rendered value>`` clauses joined by ``; `` (recursing on each
        value), so Hailuo's ``physics_keywords`` reads as
        ``fluid — water spray, fluid dynamics, surface tension; fire — ...``
        instead of a raw Python dict repr. Any other type falls back to
        ``str()``.
        """
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            return ", ".join(HailuoBuilder._render_value(item) for item in value)
        if isinstance(value, dict):
            return "; ".join(
                f"{key} — {HailuoBuilder._render_value(val)}" for key, val in value.items()
            )
        return str(value)

    def _dialect_lines(self, cli_id: str) -> str:
        """Flatten this model's yaml dialect block into newline-joined guidance.

        Reads ``rules.model(cli_id)["dialect"]`` and renders each value through
        ``_render_value`` so nested dialect (Hailuo's ``physics_keywords``) is
        surfaced as readable prose rather than a Python repr.
        """
        dialect = self.rules.model(cli_id)["dialect"]
        return "\n".join(self._render_value(v) for v in dialect.values())

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
            f"Global constraints: {'; '.join(self.rules.global_constraints(kind='still', style=mood_anchor))}"
        )
        return self.llm.parse(brief, _RenderPrompt, max_tokens=600).prompt

    def build_motion_prompt(self, shot: Shot, model_cli_id: str) -> str:
        """Build the image-to-video motion prompt; motion-only, no mood_anchor.

        The input still already carries palette/style, so this brief deliberately
        omits mood and describes only motion, pacing, and audio — the i2v rule.
        Hailuo's dialect leads with physical verbs (it drowns in adjective piles);
        dialect and constraints come from the yaml via RenderRules, not hardcoded.
        """
        brief = (
            "Write a Minimax Hailuo 02 image-to-video MOTION prompt. The still "
            "already holds the style — describe ONLY motion, camera, pacing, and audio.\n"
            f"Hailuo dialect rules:\n{self._dialect_lines(model_cli_id)}\n"
            f"Motion to animate over ~5s: {shot.motion}\n"
            f"Global constraints: {'; '.join(self.rules.global_constraints(kind='motion', style=''))}"
        )
        return self.llm.parse(brief, _RenderPrompt, max_tokens=600).prompt
