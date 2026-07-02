"""Approval CLI for the news-reactive content monitor (P3.5, Task 9).

Strings the whole monitor pipeline together and lets a human approve one angle:

    Reddit scraper -> event extractor -> idea-fit gate -> gap agent -> story
    pitcher -> craft gate (+ one bounded repair) -> [human picks a survivor] ->
    persist + emit a render handoff.

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
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from src.models.angle_pitch import AnglePitchRecord
from src.models.trending_event import TrendingEventRecord


def _print_slate(displayed: list[dict]) -> None:
    """Render the numbered story-pitch slate to stdout for the human to choose from.

    Args:
        displayed: The flat, display-ordered list of surviving pitch entries (each
            passed the craft gate). Each entry is a dict with keys ``event``
            (TrendingEvent), ``gap`` (GapAnalysis), ``pitch`` (StoryPitch), and
            ``verdict`` (StoryCraftVerdict). The list index + 1 is the selection
            number the user types.

    Side effects:
        Prints only — does not mutate the entries or the DB. The ``⚠ LEGAL FLAG``
        line is emitted for any pitch whose ``legal_flag`` is true. Credits are
        computed by ``estimate_pitch_credits`` (code, never an LLM guess).
    """
    from src.monitor.story_pitcher import estimate_pitch_credits

    last_headline = None
    for i, entry in enumerate(displayed, start=1):
        event = entry["event"]
        gap = entry["gap"]
        pitch = entry["pitch"]

        if event.headline != last_headline:
            fit = entry.get("fit")
            print("\n" + "=" * 70)
            print(f"EVENT: {event.headline}")
            heat_str = (
                (
                    f"heat={fit.heat_score:.2f}  recency={fit.recency_days:.1f}d  "
                    f"mode={fit.mode.value}  "
                )
                if fit
                else ""
            )
            print(
                f"  {heat_str}trendiness={event.trendiness_score:.2f}  "
                f"want={gap.audience_want}"
            )
            print("=" * 70)
            last_headline = event.headline

        beats_line = " → ".join(
            f"{beat.role.value}({beat.shot_size.value})" for beat in pitch.beats
        )
        print(f"\n[{i}] {pitch.logline}")
        print(
            f"     mode:   {pitch.mode.value}  (~{estimate_pitch_credits(pitch):.0f} cr)"
        )
        print(f"     beats:  {beats_line}")
        if pitch.hook_line:
            print(f'     hook:   "{pitch.hook_line}"')
        if pitch.legal_flag:
            print("     ⚠ LEGAL FLAG — depends on a real person / specific IP")


def run_pitch_pipeline(
    db,
    scraper,
    extractor,
    idea_fit_gate,
    gap_agent,
    story_pitcher,
    story_craft_gate,
    *,
    dry_run: bool,
    choice_provider: Callable[[], str] | None,
    output_dir,
    top_n: int = 3,
    context_agent=None,
    topic: str | None = None,
) -> dict | None:
    """Run the monitor pipeline, present the slate, and persist the approved angle.

    Flow: fetch raw events from ``scraper`` -> ``extractor.extract`` shortlist ->
    ``idea_fit_gate.evaluate`` kills stale / cheap-meme events -> for each
    surviving event ``gap_agent.analyze`` then ``story_pitcher.pitch`` (2-3 story
    pitches). Each pitch is judged by ``story_craft_gate.evaluate``; a failing pitch
    gets ONE bounded repair re-pitch (``story_pitcher.repitch`` with the verdict's
    failure_notes) then is re-judged. Pitches that pass are printed as one numbered
    slate; pitches that fail after repair are dropped and persisted killed_by_gate.

    Path B (--topic): when ``topic`` and ``context_agent`` are provided, the
    scraper+extractor are skipped; the agent gathers one (event, bundle) pair,
    the bundle grounds gap+pitch (``analyze(event, bundle)`` /
    ``pitch(event, gap, bundle)``), and on persist the bundle is written into
    the ``trending_events.context_bundle`` JSON column. Path A (no topic) is
    byte-for-byte today's behavior — ``bundle=None`` flows through and the
    column stays NULL.

    In ``dry_run`` the pipeline runs and prints but touches nothing: no DB writes,
    no prompt (``choice_provider`` is never called — passing ``None`` is safe), no
    handoff file. Otherwise every surfaced event and angle is persisted, the user
    is asked to pick, and the chosen angle is flagged approved.

    Args:
        db: An open SQLAlchemy session.
        scraper: Anything with ``fetch() -> list[TrendingEvent]``.  Unused when
            ``topic`` is set (Path B skips scraping); may be ``None`` then.
        extractor: Anything with ``extract(events, top_n) -> list[TrendingEvent]``.
            Unused when ``topic`` is set; may be ``None`` then.
        idea_fit_gate: Anything with ``evaluate(event) -> IdeaFitResult``.
        gap_agent: Anything with ``analyze(event, bundle=None) -> GapAnalysis``.
        story_pitcher: Anything with ``pitch(event, gap, bundle=None) -> StoryPitchSlate``
            and ``repitch(event, gap, failed_pitch, failure_notes, bundle=None) -> StoryPitch``.
        story_craft_gate: Anything with ``evaluate(pitch, event, gap) -> StoryCraftVerdict``.
        dry_run: When true, run + print only; persist nothing and never prompt.
        choice_provider: Zero-arg callable returning the user's selection as a
            string — ``"1"``..``"9"`` to approve that angle, ``"s"`` to skip/exit,
            ``"r"`` to re-pitch (not implemented in v1, treated as skip). Only
            called when ``dry_run`` is false; may be ``None`` for dry runs.
        output_dir: Directory the handoff JSON is written into (created if absent).
        top_n: Max events to carry forward from the extractor (Path A only).
        context_agent: Anything with ``gather(topic) -> (TrendingEvent, ContextBundle)``
            and a ``max_run_apify_cost`` float attribute (the returned bundle's
            ``apify_cost_estimate`` is printed against it for cost visibility).
            Required when ``topic`` is set; ignored otherwise.
        topic: When set, run Path B (user-supplied topic on-ramp); when ``None``,
            run Path A (scraper -> extractor -> ...).

    Returns:
        The handoff dict written to disk (also returned for convenience) when an
        angle is approved; ``None`` on dry runs, skips, or invalid selections.
    """
    # Path B (user topic) vs Path A (scraper).  bundles keyed by id(event) so
    # the persist loop can look up the bundle for each event without threading it
    # through every intermediate structure.
    bundles: dict[int, "object | None"] = {}

    if topic is not None:
        if context_agent is None:
            raise ValueError("context_agent is required when topic is set (Path B)")
        print(
            f"[Path B] Apify cost ceiling this run: ${context_agent.max_run_apify_cost:.2f} "
            f"(hard cap, see context_agent.py:decide_next_step)"
        )
        event, bundle = context_agent.gather(topic)
        print(f"[Path B] Apify cost spent: ${bundle.apify_cost_estimate:.2f}")
        events = [event]
        bundles[id(event)] = bundle
    else:
        raw_events = scraper.fetch()
        events = extractor.extract(raw_events, top_n=top_n)

    # Idea-fit gate: kill stale waves and cheap-meme events before spending LLM credits.
    fit_pairs: list[tuple] = []
    for event in events:
        fit = idea_fit_gate.evaluate(event)
        if fit.idea_fit:
            fit_pairs.append((event, fit))
        else:
            print(f"\n[KILLED] {event.headline[:70]!r}")
            print(
                f"         heat={fit.heat_score:.2f}  "
                f"recency={fit.recency_days:.1f}d  "
                f"mode={fit.mode.value}"
            )
            print(f"         kill_reason: {fit.kill_reason}")
            if fit.reason:
                print(f"         llm_reason:   {fit.reason}")

    if not fit_pairs:
        print("\nNo events passed the idea-fit gate.")
        if dry_run:
            print("[dry-run] nothing persisted.")
        return None

    # gap -> pitch -> craft gate (+ ONE bounded repair re-pitch). Surviving pitches
    # go on the numbered slate; pitches that still fail after repair are dropped and
    # persisted killed_by_gate=True as negative examples. When the event has a bundle
    # (Path B), it is forwarded to gap + pitch/repitch so <context> gets injected.
    displayed: list[dict] = []
    killed: list[dict] = []
    for event, fit in fit_pairs:
        bundle = bundles.get(id(event))
        gap = gap_agent.analyze(event, bundle)
        slate = story_pitcher.pitch(event, gap, bundle)
        for pitch in slate.pitches:
            verdict = story_craft_gate.evaluate(pitch, event, gap)
            if not verdict.passes and verdict.failure_notes:
                pitch = story_pitcher.repitch(
                    event, gap, pitch, verdict.failure_notes, bundle
                )
                verdict = story_craft_gate.evaluate(pitch, event, gap)
            entry = {
                "event": event,
                "fit": fit,
                "gap": gap,
                "pitch": pitch,
                "verdict": verdict,
                "bundle": bundle,
            }
            (displayed if verdict.passes else killed).append(entry)

    _print_slate(displayed)
    if not displayed:
        print("\nWave died — every pitch failed the craft gate.")

    if dry_run:
        print("\n[dry-run] nothing persisted.")
        return None

    # Persist every surfaced event once (keyed by object identity so all pitches of
    # one event — survivors and gate-killed alike — share a single row), then flush
    # to assign the PKs the FK and the handoff JSON need. When a bundle is present
    # (Path B), serialize it into the context_bundle JSON column.
    from src.monitor.story_pitcher import estimate_pitch_credits

    all_entries = displayed + killed
    event_records: dict[int, TrendingEventRecord] = {}
    now = datetime.now(timezone.utc)
    for entry in all_entries:
        event = entry["event"]
        if id(event) not in event_records:
            gap = entry["gap"]
            bundle = entry.get("bundle")
            record = TrendingEventRecord(
                run_at=now,
                source="reddit",
                headline=event.headline,
                url=event.url,
                reaction_sample=event.reaction_sample,
                trendiness_score=event.trendiness_score,
                virality_window_hours=event.virality_window_hours,
                dominant_emotion=gap.dominant_emotion,
                audience_want=gap.audience_want,
                composite_score=event.trendiness_score,
                context_bundle=bundle.model_dump() if bundle is not None else None,
                selected_for_pitching=False,
            )
            db.add(record)
            event_records[id(event)] = record
    db.flush()

    def _pitch_record(entry: dict, *, killed_by_gate: bool) -> AnglePitchRecord:
        """Build an AnglePitchRecord from a pitch entry.

        Stores the full StoryPitch and craft verdict as JSON; ``take`` keeps the
        logline as the inert writer bridge; legacy format_description/render_backend
        stay NULL. ``killed_by_gate`` marks pitches the gate dropped after repair.
        """
        pitch = entry["pitch"]
        verdict = entry["verdict"]
        return AnglePitchRecord(
            trending_event_id=event_records[id(entry["event"])].id,
            take=pitch.logline,
            estimated_cost_credits=estimate_pitch_credits(pitch),
            gap_satisfaction_rationale=pitch.why_it_lands,
            legal_flag=pitch.legal_flag,
            approved=None,
            story_json=pitch.model_dump(mode="json"),
            mode=pitch.mode.value,
            craft_verdict_json=verdict.model_dump(mode="json"),
            killed_by_gate=killed_by_gate,
        )

    # Survivor pitches are indexable so the user's number maps straight in; killed
    # pitches are persisted (killed_by_gate=True) as negative examples but not shown.
    pitch_records: list[AnglePitchRecord] = [
        _pitch_record(entry, killed_by_gate=False) for entry in displayed
    ]
    for pitch_record in pitch_records:
        db.add(pitch_record)
    for entry in killed:
        db.add(_pitch_record(entry, killed_by_gate=True))
    db.flush()

    if not pitch_records:
        db.commit()
        print("\nNo surviving pitches to approve — killed pitches saved.")
        return None

    choice = choice_provider().strip().lower() if choice_provider else "s"

    if choice in ("s", "skip", "", "q"):
        db.commit()
        print("\nSkipped — events/pitches saved, none approved.")
        return None
    if choice == "r":
        db.commit()
        print("\nRe-pitch not implemented in v1 — saved, none approved.")
        return None

    if not choice.isdigit():
        db.commit()
        print(f"\nInvalid selection {choice!r} — saved, none approved.")
        return None
    try:
        selected = int(choice)
    except ValueError:
        db.commit()
        print(f"\nInvalid selection {choice!r} — saved, none approved.")
        return None
    if not (1 <= selected <= len(pitch_records)):
        db.commit()
        print(f"\nInvalid selection {choice!r} — saved, none approved.")
        return None

    index = selected - 1
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
        "pitch_id": chosen_record.id,
        "logline": chosen_record.take,
        "mode": chosen_record.mode,
        "story": chosen_entry["pitch"].model_dump(mode="json"),
        "trendiness_score": chosen_entry["event"].trendiness_score,
        "virality_window_hours": chosen_entry["gap"].virality_window_hours,
    }
    db.commit()

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    handoff_path = out_dir / f"pitch_{handoff['pitch_id']}.json"
    handoff_path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")

    print(f"\n✓ Approved pitch [{choice}] -> {handoff_path}")
    print(
        f"  Next: uv run python scripts/smoke_content_writer.py "
        f"--pitch-id {handoff['pitch_id']} --real"
    )
    return handoff


# ---------------------------------------------------------------------------
# Production wiring (real components). Not exercised by the unit tests.
# ---------------------------------------------------------------------------


def _dataset_item_fetcher(dataset_id: str):
    """Build an item_fetcher that replays an EXISTING Apify dataset — free.

    A crashed run's scrape money isn't lost: the actor's dataset persists
    server-side and reading it back is a plain GET (no actor run, no billing).
    Injected into ApifyRedditScraper via its item_fetcher seam, so the rest of
    the pipeline is byte-identical to a live scrape; the run_input the scraper
    builds is ignored (the items already exist).
    """
    import os

    import httpx

    def _fetch(run_input: dict) -> list[dict]:
        token = os.environ.get("APIFY_API_TOKEN")
        if not token:
            raise RuntimeError("APIFY_API_TOKEN is not set — needed to read the dataset.")
        response = httpx.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
            params={"clean": "true"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    return _fetch


_DEFAULT_SUBREDDITS = [
    "manga",
    "manhwa",
    "anime",
    "WutheringWavesLeaks",
    "gaming",
    "television",
    "movies",
]


def main() -> None:
    """Parse CLI args, build the real pipeline, and run the approval loop."""
    from dotenv import load_dotenv

    load_dotenv("config/.env")

    # The slate prints Unicode glyphs (↪, ⚠, ═, em-dashes) and scraped Reddit
    # text; Windows stdout defaults to cp1252 and raises UnicodeEncodeError on
    # them. Force UTF-8 so the CLI renders on Windows consoles.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    parser = argparse.ArgumentParser(description="News-reactive angle approval CLI.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run + print the slate but persist nothing and don't prompt.",
    )
    parser.add_argument(
        "--topic",
        default=None,
        help="User-supplied topic on-ramp (Path B). When set, skips the scraper "
        "and runs the context-gathering LangGraph agent to produce a grounded "
        "ContextBundle before gate/gap/pitch. Costs ~1-2 LLM calls + 1 Apify "
        "reddit_search (cost-guarded).",
    )
    parser.add_argument(
        "--sources",
        default=None,
        help="Comma-separated subreddits to scan (default: the v1 set).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=3,
        help="Max events to carry forward from the extractor (default 3).",
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=4,
        help="Posts to scrape PER subreddit (Apify maxPostsCount is per-URL, not "
        "total). 7 subs × 4 posts × 11 items = ~$0.62/call. Apify bills per "
        "returned item (post + "
        "comment), so raising this or --comments-per-post increases cost ~linearly.",
    )
    parser.add_argument(
        "--comments-per-post",
        type=int,
        default=10,
        help="Comments to FETCH per post from Apify (maxCommentsPerPost; default "
        "10). Fetch wide enough to get good top-level reactions — actor has no "
        "top-sort, so we over-fetch then rank locally. Default 10 balances cost "
        "vs coverage. Below 5 risks missing the top-voted comments.",
    )
    parser.add_argument(
        "--top-comments",
        type=int,
        default=8,
        help="After fetching, how many TOP-LEVEL comments (ranked by upvotes) to keep "
        "in the reaction_sample that grounds the gap agent (default 8).",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Scraper only: print raw scraped events and exit (no gap/pitch/route).",
    )
    parser.add_argument(
        "--from-dataset",
        default=None,
        metavar="DATASET_ID",
        help="Replay an existing Apify dataset instead of scraping (FREE — no "
        "actor run). Recovers a crashed run's already-paid scrape; LLM stages "
        "still spend normally. Path A only.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/pitches",
        help="Where the approved-angle handoff JSON is written.",
    )
    args = parser.parse_args()

    # --no-llm is a Path A scraper-only debug mode; on the --topic path it was
    # silently ignored and the full paid pipeline ran anyway (audit AUD-H2).
    # Refuse the combination outright rather than guessing which flag wins.
    if args.topic is not None and args.no_llm:
        parser.error(
            "--no-llm and --topic are mutually exclusive: --no-llm is a Path A "
            "scraper-only debug mode; there is no free preview of Path B."
        )

    # Apify cost guard — harshmaur/reddit-scraper bills $0.002 per returned item
    # (post + every fetched comment). Rate imported from reddit_search so exactly
    # one constant exists for this actor (BUG-005: a local 0.001844 copy — a
    # different actor's rate — under-estimated ~8% and let over-threshold runs
    # pass). estimates = subreddits × max_posts × (1 + comments_per_post).
    # Refuse to run if estimated cost > $1.00 (one stuck probe in the 2026-06-29
    # session burned ~$9.40 because defaults were 10 srs × 10 posts × 50 comments).
    # Path B (--topic) bypasses this guard: it uses reddit_search in search-mode
    # (one topic, not N subreddits), cost-guarded inside the tool itself plus the
    # context agent's $2.00 run ceiling. --from-dataset also bypasses it: a
    # dataset replay is a free GET, there is no Apify spend to guard.
    if args.topic is None and args.from_dataset is None:
        from src.monitor.tools.reddit_search import _APIFY_COST_PER_ITEM
        _n_subreddits = len(_DEFAULT_SUBREDDITS) if not args.sources else len(
            [s.strip() for s in args.sources.split(",")]
        )
        _est_items = _n_subreddits * args.max_posts * (1 + args.comments_per_post)
        _est_cost = _est_items * _APIFY_COST_PER_ITEM
        if _est_cost > 1.0:
            sys.exit(
                f"Refusing to run: estimated Apify cost ${_est_cost:.2f} "
                f"(threshold $1.00). Items={_est_items} = "
                f"{_n_subreddits} subreddits × {args.max_posts} posts × "
                f"({1 + args.comments_per_post} items/post). "
                f"Pass fewer subreddits (--sources), fewer posts (--max-posts), "
                f"or fewer comments (--comments-per-post)."
            )

    from src.database import SessionLocal
    from src.monitor.event_extractor import EventExtractor
    from src.monitor.gap_agent import GapAgent
    from src.monitor.idea_fit_gate import IdeaFitGate
    from src.monitor.scraper import ApifyRedditScraper
    from src.monitor.story_craft_gate import StoryCraftGate
    from src.monitor.story_pitcher import StoryPitcher
    from src.providers.llm.anthropic_llm import AnthropicLLM
    from src.rag.embedder import BgeM3Embedder

    # Path A scraper is built first so --no-llm (a print-only debug path) can
    # return BEFORE constructing the LLM clients + BGE-M3 embedder below —
    # none of which it needs. Loading the embedding model into VRAM for a
    # plain event dump was a regression.
    if args.topic is None:
        subreddits = (
            [s.strip() for s in args.sources.split(",")]
            if args.sources
            else _DEFAULT_SUBREDDITS
        )
        if args.from_dataset:
            print(f"[replay] reading existing dataset {args.from_dataset} — no Apify spend")
        scraper = ApifyRedditScraper(
            subreddits=subreddits,
            max_posts=args.max_posts,
            fetch_comments_per_post=args.comments_per_post,
            top_comments_in_sample=args.top_comments,
            item_fetcher=(
                _dataset_item_fetcher(args.from_dataset) if args.from_dataset else None
            ),
        )
        if args.no_llm:
            for event in scraper.fetch():
                print(
                    f"[{event.trendiness_score:.0f}] r/{event.subreddit}: {event.headline}"
                )
            return
    else:
        scraper = None

    llm = AnthropicLLM(model="claude-sonnet-5")
    idea_fit_gate = IdeaFitGate(llm=llm)
    gap_agent = GapAgent(llm=llm)
    story_pitcher = StoryPitcher(llm=llm, embedder=BgeM3Embedder())
    story_craft_gate = StoryCraftGate(llm=llm)

    if args.topic is not None:
        # Path B: --topic on-ramp. Skip scraper+extractor; run context agent.
        from src.monitor.context_agent import ContextAgent

        extractor = None
        context_agent = ContextAgent(llm=llm)
        topic = args.topic
    else:
        # Path A: scraper already built above; add the extractor.
        extractor = EventExtractor(llm=llm)
        context_agent = None
        topic = None

    db = SessionLocal()
    try:
        run_pitch_pipeline(
            db,
            scraper,
            extractor,
            idea_fit_gate,
            gap_agent,
            story_pitcher,
            story_craft_gate,
            dry_run=args.dry_run,
            choice_provider=(
                None if args.dry_run else lambda: input("\nPick an angle [#/s/r]: ")
            ),
            output_dir=args.output_dir,
            top_n=args.top_n,
            context_agent=context_agent,
            topic=topic,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
