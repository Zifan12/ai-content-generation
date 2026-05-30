"""
Persistent budget tracker — the graceful (local) half of the dual guard.

Apify bills per item RETURNED by the actor, charged at fetch time before any
dedup. So spend is tracked on items returned, not items archived: the
orchestrator calls charge(len(dataset_items)) right after each run's fetch.
State persists to budget.json so spend survives across sessions/restarts.
The hard backstop is a separately-configured Apify console spend cap.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

BUDGET_NAME = "budget.json"
DEFAULT_PER_1K_USD = 0.30


class BudgetTracker:
    """
    Tracks cumulative items returned and derived USD spend against a cap.

    Persisted to budget.json on every charge so a resumed run continues from
    prior spend rather than resetting to zero.
    """

    def __init__(self, root: Path, cap_usd: float, per_1k_usd: float = DEFAULT_PER_1K_USD):
        self.root = Path(root)
        self.path = self.root / BUDGET_NAME
        self.cap_usd = cap_usd
        self.per_1k_usd = per_1k_usd
        self.items_returned = 0
        self._load()

    def _load(self) -> None:
        """Restore items_returned from budget.json if present."""
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        self.items_returned = int(data.get("items_returned", 0))

    @property
    def est_spend_usd(self) -> float:
        """Estimated USD spent: items_returned / 1000 * per_1k_usd."""
        return self.items_returned / 1000.0 * self.per_1k_usd

    def remaining(self) -> float:
        """USD remaining before the cap (may go negative if overshot)."""
        return self.cap_usd - self.est_spend_usd

    def exhausted(self) -> bool:
        """True once estimated spend reaches or exceeds the cap."""
        return self.est_spend_usd >= self.cap_usd

    def charge(self, n_items: int) -> None:
        """Add n_items returned to the running total and persist."""
        self.items_returned += int(n_items)
        self._persist()

    def _persist(self) -> None:
        """Write current state to budget.json."""
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "items_returned": self.items_returned,
            "est_spend_usd": round(self.est_spend_usd, 4),
            "budget_cap_usd": self.cap_usd,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
