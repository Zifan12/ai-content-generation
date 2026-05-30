"""
Append-only manifest + failure log for the archive.

manifest.jsonl is the queryable index — one JSON line per successfully
archived item. The set of ids it contains doubles as resume state: on
startup we load every id so re-runs skip what is already archived.

failures.jsonl records items/downloads that failed, so gaps are visible
rather than silently lost. Failures do NOT mark an id as seen — a failed
item should be retried on the next run while its source URL may still live.
"""

import json
from pathlib import Path

MANIFEST_NAME = "manifest.jsonl"
FAILURES_NAME = "failures.jsonl"


class ManifestStore:
    """
    Loads seen ids from manifest.jsonl on init; appends success/failure lines.

    Each append flushes immediately so an interrupted run leaves a readable,
    resumable manifest. A truncated final line (crash mid-write) is tolerated
    on load and skipped.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.manifest_path = self.root / MANIFEST_NAME
        self.failures_path = self.root / FAILURES_NAME
        self.seen: set[str] = set()
        self._load_seen()

    def _load_seen(self) -> None:
        """Populate self.seen from manifest.jsonl, skipping unparseable lines."""
        if not self.manifest_path.exists():
            return
        with self.manifest_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # truncated/corrupt line — skip
                item_id = record.get("id")
                if item_id is not None:
                    self.seen.add(str(item_id))

    def has(self, video_id: str) -> bool:
        """Return True if video_id is already recorded as successfully archived."""
        return str(video_id) in self.seen

    def add_success(self, record: dict) -> None:
        """Append a success record to manifest.jsonl and mark its id seen."""
        self.root.mkdir(parents=True, exist_ok=True)
        self._append(self.manifest_path, record)
        item_id = record.get("id")
        if item_id is not None:
            self.seen.add(str(item_id))

    def add_failure(self, record: dict) -> None:
        """Append a failure record to failures.jsonl (does not mark id seen)."""
        self.root.mkdir(parents=True, exist_ok=True)
        self._append(self.failures_path, record)

    @staticmethod
    def _append(path: Path, record: dict) -> None:
        """Append one JSON line (utf-8, non-ascii preserved) and flush."""
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
