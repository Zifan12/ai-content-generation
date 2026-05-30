import json

from scripts.archive import run as run_mod
from scripts.archive.seeds import Seed


def test_run_archive_loop_archives_and_dedups(tmp_path):
    # two seeds; the fake Apify returns the same item for both -> 2nd is skipped
    item = {
        "id": "v1",
        "views": 10,
        "hashtags": ["a"],
        "channel": {"username": "u"},
        "video": {"url": "https://cdn/v.mp4", "cover": "https://cdn/c.jpg"},
        "subtitleInformation": [],
    }

    class FakeApify:
        def __init__(self):
            self.calls = 0

        def run_hashtag(self, hashtag, max_items, location="US", sort_type="RELEVANCE"):
            self.calls += 1
            return [item]

    def fake_dl(url, target, timeout=60.0):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        return True

    seeds = [Seed("n", "a"), Seed("n", "b")]
    summary = run_mod.run_archive(
        root=tmp_path,
        seeds=seeds,
        client=FakeApify(),
        downloader=fake_dl,
        max_items=10,
        cap_usd=30.0,
    )

    assert summary["archived"] == 1
    assert summary["skipped"] == 1
    assert summary["failed"] == 0
    # budget charged on items RETURNED (1 per run * 2 runs = 2), not archived
    assert summary["items_returned"] == 2
    lines = (tmp_path / "manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == "v1"


def test_run_archive_stops_when_budget_exhausted(tmp_path):
    item = {"id": "v1", "video": {"url": "u"}, "hashtags": [], "channel": {}}

    class FakeApify:
        def run_hashtag(self, hashtag, max_items, location="US", sort_type="RELEVANCE"):
            return [item] * 1000  # 1000 items -> $0.30

    def fake_dl(url, target, timeout=60.0):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"x")
        return True

    seeds = [Seed("n", str(i)) for i in range(10)]
    summary = run_mod.run_archive(
        root=tmp_path,
        seeds=seeds,
        client=FakeApify(),
        downloader=fake_dl,
        max_items=1000,
        cap_usd=0.30,  # one run exhausts it
    )
    # first run charges 1000 -> exhausted; remaining seeds skipped at the gate
    assert summary["runs_executed"] == 1
