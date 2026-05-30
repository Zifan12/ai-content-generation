from scripts.archive.manifest import ManifestStore


def test_empty_store_has_no_ids(tmp_path):
    store = ManifestStore(tmp_path)
    assert not store.has("123")


def test_add_success_persists_and_marks_seen(tmp_path):
    store = ManifestStore(tmp_path)
    store.add_success({"id": "123", "path": "12/123"})
    assert store.has("123")
    # reload from disk: a fresh store sees it
    assert ManifestStore(tmp_path).has("123")


def test_add_failure_writes_failures_file(tmp_path):
    store = ManifestStore(tmp_path)
    store.add_failure({"id": "9", "stage": "video_download", "error": "404"})
    failures = (tmp_path / "failures.jsonl").read_text(encoding="utf-8")
    assert '"id": "9"' in failures
    # failures do NOT mark an id as seen
    assert not store.has("9")


def test_load_tolerates_truncated_last_line(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text('{"id": "a"}\n{"id": "b"', encoding="utf-8")
    store = ManifestStore(tmp_path)
    assert store.has("a")
    assert not store.has("b")  # truncated line skipped
