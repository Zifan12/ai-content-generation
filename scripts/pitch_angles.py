"""Approval CLI for the news-reactive content monitor (P3.5, Task 9).

Strings the whole monitor pipeline together and lets a human approve one angle:

    Reddit scraper -> event extractor -> gap agent -> angle pitcher -> format
    router -> [human picks one] -> persist + emit a render handoff.

The orchestration lives in ``run_pitch_pipeline`` which takes every component as
an argument (dependency injection) so it can be driven by fakes in tests with no
network and no real DB. The ``__main__`` block wires the real praw client, the
real LLM-backed agents, a Postgres session, and a console ``input()`` chooser.

On a real (non-dry-run) selection the chosen ``AnglePitchRecord`` is flagged
``approved=True`` and a small handoff JSON is written under ``output_dir`` (default
``output/pitches/``). Task 10's ``smoke_content_writer --pitch-id`` reads that row
back and feeds the angle's ``take`` to the writer as a premise.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.models.angle_pitch import AnglePitchRecord
from src.models.trending_event import TrendingEventRecord


def _print_slate(displayed: list[dict]) -> None:
    """Render the numbered pitch slate to stdout for the human to choose from.

    Args:
        displayed: The flat, display-ordered list of pitch entries. Each entry is
            a dict with keys ``event`` (TrendingEvent), ``gap`` (GapAnalysis),
            ``angle`` (AnglePitch), and ``decision`` (RoutingDecision). The list
            index + 1 is the selection number the user types.

    Side effects:
        Prints only — does not mutate the entries or the DB. The ``⚠ LEGAL FLAG``
        line is emitted for any angle whose ``legal_flag`` is true, and a
        ``↪ substituted`` line whenever the router downgraded the wished-for
        backend (``decision.is_substitute``).
    """
    last_headline = None
    for i, entry in enumerate(displayed, start=1):
        event = entry["event"]
        gap = entry["gap"]
        angle = entry["angle"]
        decision = entry["decision"]

        if event.headline != last_headline:
            print("\n" + "=" * 70)
            print(f"EVENT: {event.headline}")
            print(f"  trendiness={event.trendiness_score:.2f}  "
                  f"gap={gap.gap_type.value}  want={gap.audience_want}")
            print("=" * 70)
            last_headline = event.headline

        print(f"\n[{i}] {angle.take}")
        print(f"     format:   {angle.format_description}")
        print(f"     backend:  {decision.backend.value}  (~{angle.estimated_cost_credits:.0f} cr)")
        if decision.is_substitute:
            print(f"     ↪ substituted: {decision.substitution_note}")
        if angle.legal_flag:
            print("     ⚠ LEGAL FLAG — depends on a real person / specific IP")


def run_pitch_pipeline(
    db,
    scraper,
    extractor,
    gap_agent,
    angle_pitcher,
    format_router,
    *,
    dry_run: bool,
    choice_provider: Callable[[], str] | None,
    output_dir,
    top_n: int = 3,
) -> dict | None:
    """Run the monitor pipeline, present the slate, and persist the approved angle.

    Flow: fetch raw events from ``scraper`` -> ``extractor.extract`` shortlist ->
    for each surviving event ``gap_agent.analyze`` then ``angle_pitcher.pitch``
    (3 angles) -> ``format_router.route`` each angle. The combined angles are
    printed as one numbered slate.

    In ``dry_run`` the pipeline runs and prints but touches nothing: no DB writes,
    no prompt (``choice_provider`` is never called — passing ``None`` is safe), no
    handoff file. Otherwise every surfaced event and angle is persisted, the user
    is asked to pick, and the chosen angle is flagged approved.

    Args:
        db: An open SQLAlchemy session.
        scraper: Anything with ``fetch() -> list[TrendingEvent]``.
        extractor: Anything with ``extract(events, top_n) -> list[TrendingEvent]``.
        gap_agent: Anything with ``analyze(event) -> GapAnalysis``.
        angle_pitcher: Anything with ``pitch(event, gap) -> AnglePitchSlate``.
        format_router: Anything with ``route(angle) -> RoutingDecision``.
        dry_run: When true, run + print only; persist nothing and never prompt.
        choice_provider: Zero-arg callable returning the user's selection as a
            string — ``"1"``..``"9"`` to approve that angle, ``"s"`` to skip/exit,
            ``"r"`` to re-pitch (not implemented in v1, treated as skip). Only
            called when ``dry_run`` is false; may be ``None`` for dry runs.
        output_dir: Directory the handoff JSON is written into (created if absent).
        top_n: Max events to carry forward from the extractor.

    Returns:
        The handoff dict written to disk (also returned for convenience) when an
        angle is approved; ``None`` on dry runs, skips, or invalid selections.
    """
    raw_events = scraper.fetch()
    events = extractor.extract(raw_events, top_n=top_n)

    # Build the flat, display-ordered slate. One LLM gap + pitch per event; one
    # routing decision per angle.
    displayed: list[dict] = []
    for event in events:
        gap = gap_agent.analyze(event)
        slate = angle_pitcher.pitch(event, gap)
        for angle in slate.angles:
            decision = format_router.route(angle)
            displayed.append(
                {"event": event, "gap": gap, "angle": angle, "decision": decision}
            )

    _print_slate(displayed)

    if dry_run:
        print("\n[dry-run] nothing persisted.")
        return None

    if not displayed:
        print("\nNo angles to approve.")
        return None

    # Persist every surfaced event once (keyed by object identity so the three
    # angles of one event share a single row), then flush to assign the PKs the
    # FK and the handoff JSON need.
    event_records: dict[int, TrendingEventRecord] = {}
    now = datetime.now(timezone.utc)
    for entry in displayed:
        event = entry["event"]
        if id(event) not in event_records:
            gap = entry["gap"]
            record = TrendingEventRecord(
                run_at=now,
                source="reddit",
                headline=event.headline,
                reaction_sample=event.reaction_sample,
                trendiness_score=event.trendiness_score,
                virality_window_hours=event.virality_window_hours,
                dominant_emotion=gap.dominant_emotion,
                audience_want=gap.audience_want,
                gap_type=gap.gap_type.value,
                producibility_score=gap.producibility_score,
                composite_score=event.trendiness_score,
                selected_for_pitching=False,
            )
            db.add(record)
            event_records[id(event)] = record
    db.flush()

    # Persist every angle (approved=None) linked to its event row, parallel to the
    # display order so the user's number indexes straight into pitch_records.
    pitch_records: list[AnglePitchRecord] = []
    for entry in displayed:
        angle = entry["angle"]
        decision = entry["decision"]
        event_record = event_records[id(entry["event"])]
        record = AnglePitchRecord(
            trending_event_id=event_record.id,
            take=angle.take,
            format_description=angle.format_description,
            render_backend=decision.backend.value,
            estimated_cost_credits=angle.estimated_cost_credits,
            gap_satisfaction_rationale=angle.gap_satisfaction_rationale,
            legal_flag=angle.legal_flag,
            approved=None,
        )
        db.add(record)
        pitch_records.append(record)
    db.flush()

    choice = choice_provider().strip().lower() if choice_provider else "s"

    if choice in ("s", "skip", "", "q"):
        db.commit()
        print("\nSkipped — events/pitches saved, none approved.")
        return None
    if choice == "r":
        db.commit()
        print("\nRe-pitch not implemented in v1 — saved, none approved.")
        return None

    if not choice.isdigit() or not (1 <= int(choice) <= len(pitch_records)):
        db.commit()
        print(f"\nInvalid selection {choice!r} — saved, none approved.")
        return None

    index = int(choice) - 1
    chosen_entry = displayed[index]
    chosen_record = pitch_records[index]
    chosen_event_record = event_records[id(chosen_entry["event"])]

    chosen_record.approved = True
    chosen_record.approved_at = datetime.now(timezone.utc)
    chosen_event_record.selected_for_pitching = True
    db.flush()

    # Capture the values the handoff needs before commit so an expire-on-commit
    # session can't force a surprise reload mid-write.
    handoff = {
        "angle_pitch_id": chosen_record.id,
        "take": chosen_record.take,
        "routed_backend": chosen_entry["decision"].backend.value,
        "trendiness_score": chosen_entry["event"].trendiness_score,
        "gap_type": chosen_entry["gap"].gap_type.value,
        "virality_window_hours": chosen_entry["gap"].virality_window_hours,
    }
    db.commit()

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    handoff_path = out_dir / f"pitch_{handoff['angle_pitch_id']}.json"
    handoff_path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")

    print(f"\n✓ Approved angle [{choice}] -> {handoff_path}")
    print(f"  Next: uv run python scripts/smoke_content_writer.py "
          f"--pitch-id {handoff['angle_pitch_id']} --real")
    return handoff


# ---------------------------------------------------------------------------
# Production wiring (real components). Not exercised by the unit tests.
# ---------------------------------------------------------------------------

_DEFAULT_SUBREDDITS = [
    "popular", "all", "television", "soccer", "sports",
    "technology", "singularity", "movies", "games", "music",
]


def _build_reddit_client():
    """Construct a read-only praw.Reddit client from environment credentials.

    Reads ``REDDIT_CLIENT_ID`` / ``REDDIT_CLIENT_SECRET`` / ``REDDIT_USER_AGENT``
    (loaded from ``config/.env`` by the import-time dotenv load below). Imported
    lazily so the unit tests never need praw installed/configured.

    Raises:
        RuntimeError: if any of the three credentials are missing.
    """
    import praw

    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    user_agent = os.environ.get("REDDIT_USER_AGENT")
    if not (client_id and client_secret and user_agent):
        raise RuntimeError(
            "Missing Reddit credentials. Set REDDIT_CLIENT_ID, "
            "REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT in config/.env."
        )
    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )


def _load_available_backends() -> dict:
    """Read the render-backend availability flags from config/settings.yaml.

    Returns a dict mapping ``RenderBackend`` members to bool. Unlisted backends
    default to unavailable.
    """
    import yaml

    from src.monitor.schemas import RenderBackend

    repo_root = Path(__file__).resolve().parents[1]
    settings = yaml.safe_load((repo_root / "config" / "settings.yaml").read_text())
    flags = (settings or {}).get("render_backends", {})
    return {backend: bool(flags.get(backend.value, False)) for backend in RenderBackend}


def main() -> None:
    """Parse CLI args, build the real pipeline, and run the approval loop."""
    from dotenv import load_dotenv

    load_dotenv("config/.env")

    parser = argparse.ArgumentParser(description="News-reactive angle approval CLI.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run + print the slate but persist nothing and don't prompt.",
    )
    parser.add_argument(
        "--sources", default=None,
        help="Comma-separated subreddits to scan (default: the v1 set).",
    )
    parser.add_argument(
        "--top-n", type=int, default=3,
        help="Max events to carry forward from the extractor (default 3).",
    )
    parser.add_argument(
        "--no-llm", action="store_true",
        help="Scraper only: print raw scraped events and exit (no gap/pitch/route).",
    )
    parser.add_argument(
        "--output-dir", default="output/pitches",
        help="Where the approved-angle handoff JSON is written.",
    )
    args = parser.parse_args()

    from src.database import SessionLocal
    from src.monitor.angle_pitcher import AnglePitcher
    from src.monitor.event_extractor import EventExtractor
    from src.monitor.gap_agent import GapAgent
    from src.monitor.router import FormatRouter
    from src.monitor.scraper import RedditScraper
    from src.providers.llm.anthropic_llm import AnthropicLLM
    from src.rag.embedder import BgeM3Embedder

    subreddits = (
        [s.strip() for s in args.sources.split(",")] if args.sources
        else _DEFAULT_SUBREDDITS
    )
    scraper = RedditScraper(_build_reddit_client(), subreddits=subreddits)

    if args.no_llm:
        for event in scraper.fetch():
            print(f"[{event.trendiness_score:.0f}] r/{event.subreddit}: {event.headline}")
        return

    llm = AnthropicLLM(model="claude-sonnet-4-6")
    extractor = EventExtractor(llm=llm)
    gap_agent = GapAgent(llm=llm)
    angle_pitcher = AnglePitcher(llm=llm, embedder=BgeM3Embedder())
    format_router = FormatRouter(llm=llm, available_backends=_load_available_backends())

    db = SessionLocal()
    try:
        run_pitch_pipeline(
            db,
            scraper,
            extractor,
            gap_agent,
            angle_pitcher,
            format_router,
            dry_run=args.dry_run,
            choice_provider=(None if args.dry_run else lambda: input("\nPick an angle [#/s/r]: ")),
            output_dir=args.output_dir,
            top_n=args.top_n,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
