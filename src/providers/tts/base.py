"""Abstract TTS provider seat — narration synthesis for the assembly step.

Mirrors the provider-ABC pattern of src/providers/llm: a minimal interface the
pipeline codes against, with concrete vendors behind it. Current backend:
Higgsfield text2speech_v2 (higgsfield_tts.py — D7 amended 2026-07-05, billed in
render credits, ~0.15cr/line). The seat exists precisely so a vendor swap is one
new subclass, which is how the OpenAI→Higgsfield flip happened.
"""

from abc import ABC, abstractmethod


class TTSProvider(ABC):
    """Synthesizes one narration line into one audio file."""

    @abstractmethod
    def synthesize(self, text: str, out_path: str) -> str:
        """Render ``text`` as speech into ``out_path`` and return ``out_path``.

        The caller owns file naming/placement (the assembler writes one file per
        narrated shot into its work dir). Implementations must write the file
        completely before returning; the returned path is fed straight into an
        ffmpeg input.
        """
