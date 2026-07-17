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
from src.monitor.fridge import index_web_text


def _print_slate(displayed: list[dict]) -> None:
    """Render the numbered story-IDEA slate to stdout for the human to choose from.

    Slice ① (staged director): the slate is desire-only — no beats, no credits
    yet (credits are priced off the developed script's beats, which don't exist
    until the StoryArchitect runs on the picked idea).

    Args:
        displayed: The flat, display-ordered list of idea entries. Each entry is
            a dict with keys ``event`` (TrendingEvent), ``gap`` (GapAnalysis),
            and ``idea`` (IdeaPitch). The list index + 1 is the selection number
            the user types.

    Side effects:
        Prints only — does not mutate the entries or the DB. The ``⚠ LEGAL FLAG``
        line is emitted for any idea whose ``legal_flag`` is true.
    """
    last_headline = None
    for i, entry in enumerate(displayed, start=1):
        event = entry["event"]
        gap = entry["gap"]
        idea = entry["idea"]

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

        print(f"\n[{i}] {idea.logline}")
        print(f"     mode:   {idea.mode.value}")
        print(f"     moment: {idea.desired_moment}")
        print(f"     why:    {idea.why_it_lands}")
        if idea.legal_flag:
            print("     ⚠ LEGAL FLAG — depends on a real person / specific IP")


def run_pitch_pipeline(
    db,
    scraper,
    extractor,
    idea_fit_gate,
    gap_agent,
    story_pitcher,
    story_architect,
    story_craft_gate,
    *,
    dry_run: bool,
    choice_provider: Callable[[], str] | None,
    location_provider: Callable[[], str] | None = None,
    output_dir,
    top_n: int = 3,
    context_agent=None,
    topic: str | None = None,
    force: bool = False,
    single_event_bundle=None,
    embedder=None,
    grounding_checker=None,
    grounding_topic: str | None = None,
) -> dict | None:
    """Run the monitor pipeline, present the idea slate, and develop the pick.

    Flow (slice ①, staged director — pick-at-idea-level, user decision
    2026-07-16): fetch raw events from ``scraper`` -> ``extractor.extract``
    shortlist -> (Path B only) an event whose bundle has non-empty
    ``unresolved_facts`` is flagged and persisted for human review before
    ``idea_fit_gate`` even runs -> ``idea_fit_gate.evaluate`` kills stale /
    cheap-meme events -> for each surviving event ``gap_agent.analyze`` then
    ``story_pitcher.pitch`` (2-3 desire-only IDEAS). All ideas print as one
    numbered slate and persist; the human picks ONE. Only the picked idea is
    developed: ``story_architect.develop`` turns it into a StoryScript, which
    ``story_craft_gate.evaluate`` judges (plus the deterministic dialogue
    floor); a failing script gets ONE bounded repair
    (``story_architect.repair`` with the combined failure notes) then is
    re-judged. A script that still fails is persisted ``killed_by_gate=True``
    and nothing is approved. Path B survivors additionally get the grounding
    check (one bounded repair of its own, same as before).

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
        story_pitcher: Anything with ``pitch(event, gap, bundle=None) -> IdeaPitchSlate``.
        story_architect: Anything with
            ``develop(idea, event, gap, bundle=None, cast_voices="") -> StoryScript`` and
            ``repair(idea, event, gap, failed_script, failure_notes, bundle=None,
            cast_voices="") -> StoryScript``.
        story_craft_gate: Anything with ``evaluate(script, event, gap) -> StoryCraftVerdict``.
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
        force: When true, the idea-fit gate becomes ADVISORY instead of a veto:
            it still runs (its verdict is printed, including the kill reason it
            would have used), but a killed event proceeds to gap/pitch anyway,
            marked ``[FORCED]``. Two use cases: (a) a human-seeded Path B topic
            the user has already judged worth exploring — the human is the
            final approver anyway; (b) exercising the gap->pitch->craft-gate
            tail, which an honest, stingy gate can otherwise leave untested for
            weeks (5 straight kill-only runs, 2026-07-02). The craft gate is
            NOT bypassed — bad pitches still die there.
        single_event_bundle: A pre-built ContextBundle for the single event
            scraper.fetch() will return (e.g. a stored one, loaded from a
            TrendingEventRecord, not gathered live). Used INSTEAD of the
            topic/context_agent live-gather path, not in addition to it —
            ignored when topic is set. Callers that use this must ensure
            scraper.fetch() returns exactly one event (e.g. via
            _OneEventScraper); the bundle is applied to that one event only.

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
        event, bundle, web_text = context_agent.gather(topic)
        print(f"[Path B] Apify cost spent: ${bundle.apify_cost_estimate:.2f}")
        events = [event]
        bundles[id(event)] = bundle
        # Web-research fridge (Task 1.5): index the RAW web text the agent
        # gathered (and the bundle discards) so the grounding check can retrieve
        # canon to check against. Path B only; skipped on dry runs (the fridge is
        # a DB write) and when no fridge machinery was injected. The inline
        # conditions also narrow the injected Optionals to non-None for mypy.
        if grounding_checker is not None and embedder is not None and not dry_run:
            index_web_text(topic, web_text, embedder, db)
    else:
        raw_events = scraper.fetch()
        events = extractor.extract(raw_events, top_n=top_n)
        if single_event_bundle is not None:
            bundles[id(events[0])] = single_event_bundle

    # Idea-fit gate: kill stale waves and cheap-meme events before spending LLM
    # credits. With force=True the gate still runs (verdict printed for the
    # record) but a kill no longer stops the event.
    #
    # unresolved_facts check runs first: a bundle (Path B only) that flagged
    # something it couldn't verify is a different failure mode than an
    # idea-fit kill — the event isn't stale or off-topic, we just can't trust
    # an automated read of it. Persisted (unlike a normal kill) so a human can
    # review it later; gap_agent/story_pitcher/story_craft_gate never run.
    fit_pairs: list[tuple] = []
    flagged: list[tuple] = []
    for event in events:
        bundle = bundles.get(id(event))
        if topic is not None and bundle is not None and bundle.unresolved_facts:
            print(f"\n[FLAGGED] {event.headline[:70]!r} — could not verify:")
            for fact in bundle.unresolved_facts:
                print(f"           - {fact}")
            flagged.append((event, bundle.unresolved_facts))
            continue
        fit = idea_fit_gate.evaluate(event)
        if fit.idea_fit:
            fit_pairs.append((event, fit))
        elif force:
            print(f"\n[FORCED] {event.headline[:70]!r} — gate would have killed:")
            print(
                f"         heat={fit.heat_score:.2f}  "
                f"recency={fit.recency_days:.1f}d  "
                f"mode={fit.mode.value}"
            )
            print(f"         kill_reason: {fit.kill_reason}")
            if fit.reason:
                print(f"         llm_reason:   {fit.reason}")
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

    if flagged:
        if dry_run:
            print(f"\n[dry-run] {len(flagged)} flagged event(s) not persisted.")
        else:
            flagged_at = datetime.now(timezone.utc)
            for event, unresolved_facts in flagged:
                bundle = bundles.get(id(event))
                db.add(
                    TrendingEventRecord(
                        run_at=flagged_at,
                        source="reddit",
                        headline=event.headline,
                        url=event.url,
                        reaction_sample=event.reaction_sample,
                        trendiness_score=event.trendiness_score,
                        virality_window_hours=event.virality_window_hours,
                        unresolved_facts=unresolved_facts,
                        composite_score=event.trendiness_score,
                        context_bundle=bundle.model_dump() if bundle is not None else None,
                        selected_for_pitching=False,
                    )
                )
            db.commit()

    if not fit_pairs:
        print("\nNo events passed the idea-fit gate.")
        if dry_run:
            print("[dry-run] nothing persisted.")
        return None

    # gap -> idea slate (slice ①). The craft gate no longer runs here: story
    # structure doesn't exist yet. Every idea goes on the numbered slate; the
    # picked one is developed by the StoryArchitect below and judged THERE.
    # When the event has a bundle (Path B), it is forwarded to gap + pitch so
    # <context> gets injected.
    displayed: list[dict] = []
    # Grounding scope: the fridge topic to retrieve canon against. Defaults to the
    # Path B scrape ``topic``, but ``grounding_topic`` overrides it so a cheap
    # re-pitch (repitch_event.py — single_event_bundle, topic=None, no re-scrape)
    # can still ground against an already-populated fridge. Decouples "grounding
    # on + fridge scope" from "topic triggers a re-scrape".
    ground_topic = grounding_topic if grounding_topic is not None else topic

    for event, fit in fit_pairs:
        bundle = bundles.get(id(event))
        gap = gap_agent.analyze(event, bundle)
        slate = story_pitcher.pitch(event, gap, bundle)
        for idea in slate.ideas:
            displayed.append(
                {
                    "event": event,
                    "fit": fit,
                    "gap": gap,
                    "idea": idea,
                    "bundle": bundle,
                }
            )

    _print_slate(displayed)
    if not displayed:
        print("\nWave died — no ideas were pitched.")

    if dry_run:
        print("\n[dry-run] nothing persisted.")
        return None

    # Persist every surfaced event once (keyed by object identity so all ideas of
    # one event share a single row), then flush to assign the PKs the FK and the
    # handoff JSON need. When a bundle is present (Path B), serialize it into the
    # context_bundle JSON column.
    event_records: dict[int, TrendingEventRecord] = {}
    now = datetime.now(timezone.utc)
    for entry in displayed:
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

    def _idea_record(entry: dict) -> AnglePitchRecord:
        """Build an AnglePitchRecord from an idea entry (slice ①).

        Stores the desire-only IdeaPitch in ``idea_json``; ``story_json`` stays
        NULL until (and unless) this idea is picked and developed. Credits are
        0.0 here — pricing needs beats, which don't exist before development;
        the picked record's estimate is overwritten below.
        """
        idea = entry["idea"]
        return AnglePitchRecord(
            trending_event_id=event_records[id(entry["event"])].id,
            take=idea.logline,
            estimated_cost_credits=0.0,
            gap_satisfaction_rationale=idea.why_it_lands,
            legal_flag=idea.legal_flag,
            approved=None,
            idea_json=idea.model_dump(mode="json"),
            story_json=None,
            mode=idea.mode.value,
            killed_by_gate=False,
        )

    pitch_records: list[AnglePitchRecord] = [
        _idea_record(entry) for entry in displayed
    ]
    for pitch_record in pitch_records:
        db.add(pitch_record)
    db.flush()

    if not pitch_records:
        db.commit()
        print("\nNo ideas to approve — events saved.")
        return None

    choice = choice_provider().strip().lower() if choice_provider else "s"

    if choice in ("s", "skip", "", "q"):
        db.commit()
        print("\nSkipped — events/ideas saved, none approved.")
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

    idea = chosen_entry["idea"]
    event = chosen_entry["event"]
    gap = chosen_entry["gap"]
    bundle = chosen_entry.get("bundle")

    # Development (D1, slice ①): the StoryArchitect turns the picked idea into
    # a StoryScript. Cast voices load HERE now — dialogue is authored by the
    # architect, not the pitcher — so profiled characters speak in-character
    # and the deterministic dialogue floor (Q3-B) has something to check.
    from src.generation.story_architect import estimate_script_credits
    from src.monitor.voice_profiles import (
        check_dialogue_floor,
        format_cast_voices,
        load_cast_profiles,
    )

    cast_profiles = load_cast_profiles()
    cast_slugs = set(cast_profiles)
    cast_voices = format_cast_voices(cast_profiles)

    print(f"\n[develop] architect is developing: {idea.logline}")
    script = story_architect.develop(idea, event, gap, bundle, cast_voices=cast_voices)

    # Craft gate + dialogue floor, ONE bounded repair on the combined notes —
    # the same bounded-retry convention the gate always used, re-targeted at
    # the architect (spec 2026-07-16 decision 3).
    verdict = story_craft_gate.evaluate(script, event, gap)
    floor_ok, floor_reason = check_dialogue_floor(script, cast_slugs)
    if not verdict.passes or not floor_ok:
        notes = "\n".join(n for n in (verdict.failure_notes, floor_reason) if n)
        if notes:
            print("[develop] script failed the gate — one bounded repair...")
            script = story_architect.repair(
                idea, event, gap, script, notes, bundle, cast_voices=cast_voices
            )
            verdict = story_craft_gate.evaluate(script, event, gap)
            floor_ok, _ = check_dialogue_floor(script, cast_slugs)

    # Grounding check (Task 1.5): craft-survivors only, scoped to
    # ``ground_topic``. A contradiction with the fridge's canon gets ONE
    # bounded repair (with the conflicts as failure notes), then grounding is
    # re-checked — craft is NOT re-judged (ADR-0008 / Q6: the human approval +
    # watch verdict backstop a craft regression from a grounding fix). The
    # floor IS re-checked: it's a cheap deterministic gate, and a repair that
    # drops the profiled speaker's line must kill the script, not slip through.
    grounding = None
    if (
        verdict.passes
        and grounding_checker is not None
        and embedder is not None
        and ground_topic is not None
    ):
        grounding = grounding_checker.check(script, ground_topic, embedder, db)
        if not grounding.coheres and grounding.conflicts:
            script = story_architect.repair(
                idea, event, gap, script, "; ".join(grounding.conflicts), bundle,
                cast_voices=cast_voices,
            )
            grounding = grounding_checker.check(script, ground_topic, embedder, db)
            floor_ok, _ = check_dialogue_floor(script, cast_slugs)

    chosen_record.story_json = script.model_dump(mode="json")
    chosen_record.estimated_cost_credits = estimate_script_credits(script)
    chosen_record.craft_verdict_json = verdict.model_dump(mode="json")
    chosen_record.grounding_verdict_json = (
        grounding.model_dump(mode="json") if grounding is not None else None
    )

    passes_all = (
        verdict.passes and floor_ok and (grounding is None or grounding.coheres)
    )
    if not passes_all:
        chosen_record.killed_by_gate = True
        db.commit()
        print("\nScript failed the gates after one repair — persisted killed_by_gate.")
        if verdict.failure_notes:
            print(f"  craft: {verdict.failure_notes}")
        if not floor_ok:
            print("  floor: a profiled on-screen character never speaks")
        if grounding is not None and not grounding.coheres:
            print(f"  grounding: {'; '.join(grounding.conflicts)}")
        return None

    # Show the human what got developed before they tag the location.
    print(f"\n[script] scene: {script.scene_setting}")
    for i, beat in enumerate(script.beats):
        line = f"  beat {i} [{beat.role.value}({beat.shot_size.value})] {beat.visual_line}"
        if beat.dialogue_line:
            line += f'  || {beat.speaker}: "{beat.dialogue_line}"'
        print(line)
    print(f"[script] ~{chosen_record.estimated_cost_credits:.0f} cr")

    chosen_record.approved = True
    chosen_record.approved_at = datetime.now(timezone.utc)
    chosen_event_record.selected_for_pitching = True

    # Location tag (spec 2026-07-11): the human declares which shared
    # refs/_location/<slug>/ folder this script renders in. Blank = ungrounded
    # location; the render's reference check reads this back and --location can
    # still backfill it later.
    slug = location_provider().strip() if location_provider else ""
    chosen_record.location_slug = slug or None
    if slug:
        print(f"[location] tagged {slug!r}")

    db.flush()

    # Capture the values the handoff needs before commit so an expire-on-commit
    # session can't force a surprise reload mid-write.
    handoff = {
        "pitch_id": chosen_record.id,
        "logline": chosen_record.take,
        "mode": chosen_record.mode,
        "story": script.model_dump(mode="json"),
        "trendiness_score": chosen_entry["event"].trendiness_score,
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
        "--force",
        action="store_true",
        help="Path B (--topic) only: make the idea-fit gate advisory instead of "
        "a veto — its verdict still prints, but a killed event proceeds to "
        "gap/pitch anyway, marked [FORCED]. The craft gate still applies. Use "
        "for human-seeded premises you've already judged worth exploring, or "
        "to exercise the pitch tail when the gate is (correctly) killing "
        "everything.",
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

    # --force is a per-premise human override; on Path A it would bypass the
    # gate for a whole scraped slate at once, which is a different (and wrong)
    # product — the gate IS the automation's editorial judgment there.
    if args.force and args.topic is None:
        parser.error(
            "--force requires --topic: the override is for a single human-seeded "
            "premise (Path B), not for un-gating a whole Path A scan."
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
    # context agent's $1.00 run ceiling. --from-dataset also bypasses it: a
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
    from src.generation.story_architect import StoryArchitect
    from src.monitor.event_extractor import EventExtractor
    from src.monitor.gap_agent import GapAgent
    from src.monitor.idea_fit_gate import IdeaFitGate
    from src.monitor.scraper import ApifyRedditScraper
    from src.monitor.story_craft_gate import StoryCraftGate
    from src.monitor.story_pitcher import StoryPitcher
    from src.providers.llm.factory import llm_for_seat
    from src.monitor.pitch_grounding import PitchGroundingChecker
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

    # Per-seat LLMs from config/providers.yaml (AUD-M21): swapping any seat's
    # provider/model is a YAML edit, not a code change.
    idea_fit_gate = IdeaFitGate(llm=llm_for_seat("idea_fit_gate"))
    gap_agent = GapAgent(llm=llm_for_seat("gap_agent"))
    # One embedder, shared by the pitcher's RAG and the web-research fridge
    # (index + grounding retrieval) — a second BgeM3Embedder would reload ~2.27GB.
    embedder = BgeM3Embedder()
    story_pitcher = StoryPitcher(llm=llm_for_seat("story_pitcher"), embedder=embedder)
    story_architect = StoryArchitect(llm=llm_for_seat("story_architect"))
    story_craft_gate = StoryCraftGate(llm=llm_for_seat("story_craft_gate"))

    if args.topic is not None:
        # Path B: --topic on-ramp. Skip scraper+extractor; run context agent.
        from src.monitor.context_agent import ContextAgent

        extractor = None
        context_agent = ContextAgent(llm=llm_for_seat("context_agent"))
        # Grounding check is Path B only — Path A gathers no web text, so the
        # fridge stays empty and there is nothing to check against (Task 1.5).
        grounding_checker = PitchGroundingChecker(llm=llm_for_seat("pitch_grounding"))
        topic = args.topic
    else:
        # Path A: scraper already built above; add the extractor.
        extractor = EventExtractor(llm=llm_for_seat("event_extractor"))
        context_agent = None
        grounding_checker = None
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
            story_architect,
            story_craft_gate,
            dry_run=args.dry_run,
            choice_provider=(
                None if args.dry_run else lambda: input("\nPick an angle [#/s/r]: ")
            ),
            location_provider=(
                None
                if args.dry_run
                else lambda: input(
                    "\nLocation slug (folder under refs/_location/, blank = none): "
                )
            ),
            output_dir=args.output_dir,
            top_n=args.top_n,
            context_agent=context_agent,
            topic=topic,
            force=args.force,
            embedder=embedder,
            grounding_checker=grounding_checker,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
