import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "gen_voice_profile",
    Path(__file__).resolve().parents[2] / "scripts" / "gen_voice_profile.py",
)
gvp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gvp)


def test_find_fandom_url_prefers_fandom_domain():
    urls = ["https://example.com/x", "https://wistoria.fandom.com/wiki/Elfaria"]
    assert gvp.find_fandom_url("...", urls) == "https://wistoria.fandom.com/wiki/Elfaria"


def test_find_fandom_url_none_when_no_fandom():
    assert gvp.find_fandom_url("...", ["https://example.com/x"]) is None


def test_build_profile_markdown_has_three_sections():
    profile = gvp.VoiceProfile(
        fingerprint="Clipped, formal; addresses others by title.",
        modulation="Softens with kin; sharpens when challenged.",
        anti_patterns=['WRONG: "We should retreat." RIGHT: "We fall back. Now."'],
    )
    md = gvp.build_profile_markdown(profile)
    assert "## Fingerprint" in md
    assert "## Modulation" in md
    assert "## Anti-patterns" in md
    assert "We fall back. Now." in md


def test_scrape_fandom_uses_injected_client_full_page():
    class _Doc:
        markdown = "## Personality\nElfaria is stern."

    class _Client:
        def __init__(self):
            self.kwargs = None

        def scrape(self, url, **kwargs):
            self.kwargs = kwargs
            return _Doc()

    client = _Client()
    text = gvp._scrape_fandom("https://x.fandom.com/wiki/Y", client=client)
    assert "Elfaria is stern." in text
    # full page, NOT the infobox-only path
    assert client.kwargs.get("only_main_content") is True
    assert "include_tags" not in client.kwargs
