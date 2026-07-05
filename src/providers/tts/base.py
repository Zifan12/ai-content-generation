"""Abstract TTS provider seat — narration synthesis for the assembly step.

Mirrors the provider-ABC pattern of src/providers/llm: a minimal interface the
pipeline codes against, with concrete vendors behind it (OpenAI today; the
Higgsfield-native text2speech_v2 surfaced in the CLI 1.1.5 catalog is the
logged alternative — spec 2026-07-04 §6.5 — to compare before locking a voice).
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
