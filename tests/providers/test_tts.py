"""Tests for the TTS provider seat (Task 7, D7 amended to Higgsfield-native).

No network, no credits: CLI runner and downloader injected.
"""

from src.providers.tts.higgsfield_tts import (
    DEFAULT_VARIANT,
    DEFAULT_VOICE_ID,
    DEFAULT_VOICE_TYPE,
    HiggsfieldTTS,
)


class FakeCLI:
    def __init__(self):
        self.argv = None

    def __call__(self, argv):
        self.argv = argv
        return "https://cdn.example/narration_abc.mp3"


def _fake_download(url, dest):
    with open(dest, "wb") as f:
        f.write(url.encode())
    return dest


def test_synthesize_builds_cli_call_and_downloads(tmp_path):
    cli = FakeCLI()
    tts = HiggsfieldTTS(run_cli=cli, download=_fake_download)
    out = str(tmp_path / "narr_0.mp3")

    returned = tts.synthesize("She waited for the signal.", out)

    assert returned == out
    assert (tmp_path / "narr_0.mp3").read_bytes() == b"https://cdn.example/narration_abc.mp3"
    assert cli.argv[:4] == ["higgsfield", "generate", "create", "text2speech_v2"]
    assert cli.argv[cli.argv.index("--prompt") + 1] == "She waited for the signal."
    assert cli.argv[cli.argv.index("--variant") + 1] == DEFAULT_VARIANT
    assert cli.argv[cli.argv.index("--voice_id") + 1] == DEFAULT_VOICE_ID
    assert cli.argv[cli.argv.index("--voice_type") + 1] == DEFAULT_VOICE_TYPE
    assert cli.argv[-1] == "--wait"


def test_voice_and_variant_overridable(tmp_path):
    cli = FakeCLI()
    tts = HiggsfieldTTS(
        variant="minimax", voice_id="abc-123", voice_type="element",
        run_cli=cli, download=_fake_download,
    )
    tts.synthesize("line", str(tmp_path / "n.mp3"))
    assert cli.argv[cli.argv.index("--variant") + 1] == "minimax"
    assert cli.argv[cli.argv.index("--voice_id") + 1] == "abc-123"
    assert cli.argv[cli.argv.index("--voice_type") + 1] == "element"
