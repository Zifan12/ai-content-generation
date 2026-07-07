"""Re-pitch ONE already-stored TrendingEventRecord through the rebuilt v2 pitcher/
gate (Tasks 2-3), without re-scraping — the event already passed idea-fit once.

Reuses scripts/pitch_angles.py's run_pitch_pipeline UNCHANGED: a one-item fake
scraper/extractor feed the stored event back through the real idea_fit_gate ->
gap_agent -> story_pitcher -> story_craft_gate -> human-approval -> persist
flow, so this event's persisted rows are identical in shape to a live scan.

USAGE:
    uv run python scripts/repitch_event.py --event-id 8
    uv run python scripts/repitch_event.py --event-id 8 --choice 1
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv("config/.env")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

from scripts.pitch_angles import run_pitch_pipeline  # noqa: E402
from src.database import SessionLocal  # noqa: E402
from src.models.trending_event import TrendingEventRecord  # noqa: E402
from src.monitor.gap_agent import GapAgent  # noqa: E402
from src.monitor.idea_fit_gate import IdeaFitGate  # noqa: E402
from src.monitor.schemas import TrendingEvent  # noqa: E402
from src.monitor.story_craft_gate import StoryCraftGate  # noqa: E402
from src.monitor.story_pitcher import StoryPitcher  # noqa: E402
from src.providers.llm.factory import llm_for_seat  # noqa: E402
from src.rag.embedder import BgeM3Embedder  # noqa: E402


class _OneEventScraper:
    def __init__(self, event: TrendingEvent):
        self._event = event

    def fetch(self) -> list[TrendingEvent]:
        return [self._event]


class _IdentityExtractor:
    def extract(self, events: list[TrendingEvent], top_n: int) -> list[TrendingEvent]:
        return events


def load_event(db, event_id: int) -> TrendingEvent:
    """Reconstruct a TrendingEvent from a stored TrendingEventRecord.

    subreddit is not a persisted column (only `source` is) — falls back to
    record.source. Display/grounding field only. raw_source_data is likewise
    not persisted, so it round-trips as an empty dict.

    origin is set to "manual" (not "scraped", even though the event was
    originally scraped) purely to steer the idea-fit gate: a stored event has
    no round-trippable timestamp, so the gate's recency sub-gate would read it
    as 999 days old and auto-kill every re-pitch. The "manual" branch skips
    only that recency kill (same as a user-typed --topic, which also has no
    createdAt); the payoff hard-kill still applies. origin is not a persisted
    column, so this white-lie about provenance affects nothing downstream.
    """
    record = db.get(TrendingEventRecord, event_id)
    if record is None:
        raise SystemExit(f"No TrendingEventRecord with id={event_id}.")
    return TrendingEvent(
        headline=record.headline,
        subreddit=record.source,
        url=record.url or "",
        reaction_sample=record.reaction_sample,
        trendiness_score=record.trendiness_score,
        virality_window_hours=record.virality_window_hours,
        raw_source_data={},
        origin="manual",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-pitch one stored event.")
    parser.add_argument("--event-id", type=int, required=True)
    parser.add_argument("--output-dir", default="output/pitches")
    parser.add_argument(
        "--choice",
        default=None,
        help="Non-interactive selection ('1'..'9', 's', or 'r') — skips the "
        "input() prompt so the run can be driven without a human at the "
        "keyboard. When omitted, prompts interactively as usual.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Make the idea-fit gate advisory instead of a veto: its verdict "
        "still prints (including the kill reason it would have used), but a "
        "killed event proceeds to gap/pitch anyway, marked [FORCED]. The craft "
        "gate still applies. Use when re-pitching a stored event the gate is "
        "(over-)stingily killing and you've judged it worth exercising the "
        "pitch tail on.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        event = load_event(db, args.event_id)
    finally:
        db.close()

    idea_fit_gate = IdeaFitGate(llm=llm_for_seat("idea_fit_gate"))
    gap_agent = GapAgent(llm=llm_for_seat("gap_agent"))
    story_pitcher = StoryPitcher(llm=llm_for_seat("story_pitcher"), embedder=BgeM3Embedder())
    story_craft_gate = StoryCraftGate(llm=llm_for_seat("story_craft_gate"))

    choice_provider = (
        (lambda: args.choice)
        if args.choice is not None
        else (lambda: input("\nPick an angle [#/s/r]: "))
    )

    db = SessionLocal()
    try:
        run_pitch_pipeline(
            db,
            _OneEventScraper(event),
            _IdentityExtractor(),
            idea_fit_gate,
            gap_agent,
            story_pitcher,
            story_craft_gate,
            dry_run=False,
            choice_provider=choice_provider,
            output_dir=args.output_dir,
            top_n=1,
            force=args.force,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
