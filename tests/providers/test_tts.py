"""Tests for the TTS provider seat (plan 2026-07-04 Task 7). No network."""

from contextlib import contextmanager

from src.providers.tts.openai_tts import DEFAULT_MODEL, DEFAULT_VOICE, OpenAITTS


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def stream_to_file(self, path):
        with open(path, "wb") as f:
            f.write(self._payload)


class _FakeSpeechAPI:
    def __init__(self):
        self.last_kwargs = None

    @contextmanager
    def create(self, **kwargs):
        self.last_kwargs = kwargs
        yield _FakeResponse(b"FAKE_AUDIO_BYTES")


class _FakeClient:
    def __init__(self):
        self.speech_api = _FakeSpeechAPI()

    @property
    def audio(self):
        client = self

        class _Audio:
            class speech:
                with_streaming_response = client.speech_api

        return _Audio


def test_synthesize_writes_file_and_passes_voice_model(tmp_path):
    fake = _FakeClient()
    tts = OpenAITTS(client=fake)
    out = str(tmp_path / "narr_0.mp3")

    returned = tts.synthesize("She waited for the signal.", out)

    assert returned == out
    assert (tmp_path / "narr_0.mp3").read_bytes() == b"FAKE_AUDIO_BYTES"
    assert fake.speech_api.last_kwargs == {
        "model": DEFAULT_MODEL,
        "voice": DEFAULT_VOICE,
        "input": "She waited for the signal.",
    }


def test_voice_and_model_overridable(tmp_path):
    fake = _FakeClient()
    tts = OpenAITTS(client=fake, voice="nova", model="gpt-4o-mini-tts")
    tts.synthesize("line", str(tmp_path / "n.mp3"))
    assert fake.speech_api.last_kwargs["voice"] == "nova"
    assert fake.speech_api.last_kwargs["model"] == "gpt-4o-mini-tts"
