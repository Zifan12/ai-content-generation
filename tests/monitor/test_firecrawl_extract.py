"""Unit tests for the firecrawl_extract full-page-fetch tool.

All tests inject ``client`` so parsing/shaping is exercised with no network
and no Firecrawl API key.
"""

import pytest

from src.monitor.tools._types import ToolResult
from src.monitor.tools.firecrawl_extract import firecrawl_extract


class _FakeDoc:
    def __init__(self, markdown):
        self.markdown = markdown


class _FakeClient:
    def __init__(self, markdown=None, raises=None):
        self._markdown = markdown
        self._raises = raises
        self.calls = []

    def scrape(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._raises is not None:
            raise self._raises
        return _FakeDoc(self._markdown)


def test_returns_markdown_content():
    client = _FakeClient(markdown="## Age\n\n16")
    result = firecrawl_extract(
        "https://wistoria.fandom.com/wiki/Elfaria", client=client
    )
    assert result == ToolResult(text="## Age\n\n16", urls=[])


def test_targets_infobox_only():
    client = _FakeClient(markdown="content")
    firecrawl_extract("https://example.com/wiki/X", client=client)
    url, kwargs = client.calls[0]
    assert url == "https://example.com/wiki/X"
    assert kwargs["only_main_content"] is True
    assert kwargs["include_tags"] == ["aside.portable-infobox"]


def test_missing_markdown_returns_empty_text():
    client = _FakeClient(markdown=None)
    result = firecrawl_extract("https://example.com", client=client)
    assert result == ToolResult(text="", urls=[])


def test_no_api_key_raises(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FIRECRAWL_API_KEY"):
        firecrawl_extract("https://example.com", api_key=None, client=None)
