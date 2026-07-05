"""OpenAI text-to-speech provider (PLAN.md tech stack: "TTS: OpenAI TTS").

Call shape verified against the openai-python SDK docs (context7, 2026-07-05):
``client.audio.speech.with_streaming_response.create(...)`` streamed to a file.

The account's narrator voice is deliberately ONE obvious constant to change —
picking it is the user's taste call at the first assembly run (spec §6.1).
"""

from src.providers.tts.base import TTSProvider

# The account narrator voice + model — change HERE (user taste call, spec §6.1).
DEFAULT_VOICE = "onyx"
DEFAULT_MODEL = "tts-1"


class OpenAITTS(TTSProvider):
    """TTSProvider backed by the OpenAI speech endpoint.

    The client is injected for tests (anything exposing
    ``audio.speech.with_streaming_response.create``); when None, a real
    ``openai.OpenAI()`` is constructed lazily on first use so importing this
    module never requires credentials.
    """

    def __init__(self, client=None, *, voice: str = DEFAULT_VOICE, model: str = DEFAULT_MODEL):
        self._client = client
        self.voice = voice
        self.model = model

    def _ensure_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI()
        return self._client

    def synthesize(self, text: str, out_path: str) -> str:
        """Render ``text`` to speech at ``out_path`` (format from the extension,
        mp3 by default on the API side) and return ``out_path``."""
        client = self._ensure_client()
        with client.audio.speech.with_streaming_response.create(
            model=self.model,
            voice=self.voice,
            input=text,
        ) as response:
            response.stream_to_file(out_path)
        return out_path
