"""Abstract contract for model-specific render prompt builders.

A PromptBuilder turns a writer Shot into the prose prompt a specific video
model wants. Each Higgsfield model speaks a slightly different dialect (Veo
wants shot-beats + an Audio line, Hailuo wants restrained physics-verbs), so
there is one concrete builder per model — but the RenderAdapter depends on this
ABC, not the concretes, so Veo and Hailuo are interchangeable behind the same
two-method interface.

Builders own their dialect-flattening: most models store flat string dialect
values (Veo), but some store nested structures (Hailuo's ``physics_keywords``
is a dict of lists), and the right way to render those into an LLM brief
differs per model. Keeping each builder's logic separate lets each flatten its
own dialect correctly instead of forcing one shared helper to handle every
shape.
"""

from abc import ABC, abstractmethod

from src.schemas.generation import Shot


class PromptBuilder(ABC):
    """The interface every per-model prompt builder must implement.

    Two prompts come out of the render layer for a shot: the opening STILL
    (an image prompt) and the MOTION that animates it (an image-to-video
    prompt). They have opposite rules about style, which is the load-bearing
    contract this ABC encodes:

      - build_still_prompt is the ONE place ``mood_anchor`` belongs — the
        generated still carries the palette / lighting / grade for the whole
        video.
      - build_motion_prompt must NOT restate ``mood_anchor`` — the still
        already holds the style, and re-describing it in an i2v motion prompt
        degrades motion quality. The motion prompt is motion-only.

    Subclasses (VeoBuilder, HailuoBuilder) fill both methods using their
    model's dialect block from RenderRules. This class cannot be instantiated
    directly; doing so raises TypeError until both abstract methods are
    implemented.
    """

    @abstractmethod
    def build_still_prompt(self, shot: Shot, mood_anchor: str) -> str:
        """Build the prompt for the opening still image of a shot.

        This is the only builder method that consumes ``mood_anchor`` — the
        still it produces is what carries palette, lighting, realism and the
        uncanny register for the entire video. Returns the model-native image
        prompt as prose.
        """
        ...

    @abstractmethod
    def build_motion_prompt(self, shot: Shot, model_cli_id: str) -> str:
        """Build the image-to-video motion prompt that animates the still.

        Motion-only by contract: it must NOT restate ``mood_anchor`` or
        otherwise re-describe the still's contents (palette, scene, style) —
        the input still already carries those, and repeating them reduces i2v
        motion quality. It describes camera movement, subject motion, timing
        and audio, phrased in ``model_cli_id``'s dialect. Returns prose.
        """
        ...
