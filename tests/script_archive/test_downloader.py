import httpx
import respx

from scripts.archive.downloader import download


@respx.mock
def test_download_writes_bytes_on_200(tmp_path):
    url = "https://cdn.example/video.mp4"
    respx.get(url).mock(return_value=httpx.Response(200, content=b"\x00\x01\x02"))
    target = tmp_path / "sub" / "video.mp4"
    ok = download(url, target)
    assert ok is True
    assert target.read_bytes() == b"\x00\x01\x02"


@respx.mock
def test_download_returns_false_on_404(tmp_path):
    url = "https://cdn.example/gone.mp4"
    respx.get(url).mock(return_value=httpx.Response(404))
    target = tmp_path / "video.mp4"
    ok = download(url, target)
    assert ok is False
    assert not target.exists()


@respx.mock
def test_download_returns_false_on_network_error(tmp_path):
    url = "https://cdn.example/boom.mp4"
    respx.get(url).mock(side_effect=httpx.ConnectError("boom"))
    ok = download(url, tmp_path / "video.mp4")
    assert ok is False
