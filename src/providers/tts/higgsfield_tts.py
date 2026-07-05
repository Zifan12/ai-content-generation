"""Higgsfield-native text-to-speech provider (D7 amended 2026-07-05).

Replaces the OpenAI TTS pick: config/.env holds no OPENAI_API_KEY (a new vendor
account for narration only), while Higgsfield's ``text2speech_v2`` job type is
billed through the already-funded credit plan AND exposes an ``elevenlabs``
variant — the premium-TTS quality tier without an ElevenLabs account. Measured
cost: 0.15 credits per narration line (CLI quote, 2026-07-05).

CLI shape (``higgsfield model get text2speech_v2``, 1.1.5): prompt + variant
(elevenlabs/minimax/seed_speech/vibe_voice/cozy_voice) + voice_id + voice_type,
voice ids from ``higgsfield voices list``. Char limit 5000 on the elevenlabs
variant — a narration line is ~15 words, never close.

Reuses the executor's CLI/download helpers (they are the project's one
Higgsfield-CLI seam; duplicating them here would just rot separately).
"""

from src.generation.executor import _download, _extract_url, _run_cli
from src.providers.tts.base import TTSProvider

# The account narrator voice — change HERE after auditioning `higgsfield voices
# list` (user taste call, spec §6.1). Sterling is an unratified placeholder.
DEFAULT_VARIANT = "elevenlabs"
DEFAULT_VOICE_ID = "dc382508-c8bd-443c-8cb2-46e57b8d2e6f"  # "Sterling" (preset)
DEFAULT_VOICE_TYPE = "preset"


class HiggsfieldTTS(TTSProvider):
    """TTSProvider backed by the Higgsfield CLI's text2speech_v2 job type.

    Costs credits (~0.15/line measured) rather than a separate API bill; the
    run_cli/download boundaries are injected for tests, mirroring the executor.
    """

    def __init__(
        self,
        *,
        variant: str = DEFAULT_VARIANT,
        voice_id: str = DEFAULT_VOICE_ID,
        voice_type: str = DEFAULT_VOICE_TYPE,
        run_cli=_run_cli,
        download=_download,
    ):
        self.variant = variant
        self.voice_id = voice_id
        self.voice_type = voice_type
        self._run_cli = run_cli
        self._download = download

    def synthesize(self, text: str, out_path: str) -> str:
        """Render ``text`` via text2speech_v2 and download it to ``out_path``."""
        output = self._run_cli(
            [
                "higgsfield", "generate", "create", "text2speech_v2",
                "--prompt", text,
                "--variant", self.variant,
                "--voice_id", self.voice_id,
                "--voice_type", self.voice_type,
                "--wait",
            ]
        )
        return self._download(_extract_url(output), out_path)
