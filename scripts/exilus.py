"""Exilus: topic-in -> idea-slate-out orchestrator (PRD 2026-07-17, ticket 07).

Strings the four Exilus stages together the way ``run_pitch_pipeline``
(``scripts/pitch_angles.py``) strings the legacy Path A/B chain:

    research (ContextAgent.gather_brief) -> checker + bounded repair
    (brief_checker.check_and_repair_brief) -> faction read (FactionReader) ->
    ideation (Ideator) -> [human picks] -> persist + handoff

Two pinned artifacts (``TopicBrief``, ``FactionMap``) are written ONCE per
topic (``src.monitor.topic_brief`` / ``src.monitor.faction_reader``). A plain
re-roll (no ``--refresh``) loads the pinned pair and calls ONLY the ideation
stage, threading the topic's previously-shown idea loglines in as a
do-not-repeat list; ``--refresh`` re-runs research/checker/faction regardless
of pinned state and REPLACES the stored artifacts + fridge rows (never
stacks). A brief that still has UNVERIFIED fields after the checker's 2-round
repair budget is persisted as-is and the run HALTS before faction/ideation
ever run — the operator must inspect and either fix the source material or
force a fresh run.

The picked idea persists as an ``AnglePitchRecord`` (the same table/columns
``pitch_angles.py`` uses, ``idea_json`` only — this ticket stops before the
StoryArchitect, which is explicitly out of scope: see the ticket's "Out of
Scope"). The handoff JSON therefore carries the same identifying keys
(``pitch_id``/``logline``/``mode``/``trendiness_score``) but has no ``story``
key — there is no developed script yet at this stage of the pipeline.

The orchestration lives in ``run_exilus_pipeline`` which takes every
component as an argument (dependency injection), same as
``run_pitch_pipeline``, so it is driven by fakes in tests with no network and
no real DB. The ``__main__`` block wires the real ``ContextAgent``,
``FactionReader``, ``Ideator``, a Postgres session, and a console ``input()``
chooser.
"""

import argparse
import json
import re
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from src.models.angle_pitch import AnglePitchRecord
from src.models.trending_event import TrendingEventRecord
from src.monitor.brief_checker import check_and_repair_brief
from src.monitor.faction_reader import load_faction_map, save_faction_map
from src.monitor.fridge import replace_topic_material
from src.monitor.schemas import ExilusSlate, FactionMap, TopicBrief
from src.monitor.topic_brief import load_topic_brief, save_topic_brief

# Mirrors brief_checker._MAX_REPAIR_ROUNDS's value (PRD: "max 2 fail-and-repair
# rounds") -- not imported (that name is private to its module), just the same
# number, overridable per-call the same way check_and_repair_brief's own
# parameter is.
_MAX_REPAIR_ROUNDS = 2

# The four TopicBrief fields the checker can stamp UNVERIFIED -- used only to
# report which fields halted the run; brief_checker._CHECKED_FIELDS is the
# authoritative (private) source, reproduced here for the halt-notice printer.
_CHECKED_FIELDS = ("identity", "recent_events", "key_characters", "why_people_care")


def _topic_slug(topic: str) -> str:
    """Filesystem-safe slug for a topic name (dump/import artifact filenames)."""
    return re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_") or "topic"


def _find_or_create_event(db, topic: str) -> TrendingEventRecord:
    """Find-or-create the topic's manual-origin TrendingEventRecord.

    Reuses Path B's manual-event pattern (D8) so AnglePitchRecord's existing
    FK contract holds: every idea an Exilus run ever surfaces for ``topic``
    (across fresh runs, refreshes, and re-rolls) hangs off exactly ONE event
    row, found by ``headline == topic``. ``.first()`` (not ``.one_or_none()``)
    is deliberately tolerant of more than one matching row rather than raising
    -- the earliest-created row is treated as canonical.
    """
    record = (
        db.query(TrendingEventRecord)
        .filter_by(headline=topic)
        .order_by(TrendingEventRecord.id)
        .first()
    )
    if record is None:
        record = TrendingEventRecord(
            run_at=datetime.now(timezone.utc),
            source="manual",
            headline=topic,
            url=None,
            reaction_sample="",
            trendiness_score=0.0,
            virality_window_hours=24.0,
            selected_for_pitching=False,
        )
        db.add(record)
        db.flush()
    return record


def _prior_loglines(db, event_id: int) -> tuple[str, ...]:
    """Loglines of every idea already persisted for this topic's event, oldest first.

    The re-roll do-not-repeat list (AC5): every slate a prior Exilus run (fresh
    or re-roll) surfaced for this topic persisted its ideas as AnglePitchRecord
    rows keyed by this event id (see ``_idea_record`` / ``_find_or_create_event``)
    -- this query is simply "every idea this topic has ever shown."
    """
    rows = (
        db.query(AnglePitchRecord.take)
        .filter_by(trending_event_id=event_id)
        .order_by(AnglePitchRecord.id)
        .all()
    )
    return tuple(row[0] for row in rows)


def _idea_record(event_id: int, idea) -> AnglePitchRecord:
    """Build an AnglePitchRecord from one ExilusIdea (idea_json only, no story yet).

    Mirrors ``pitch_angles.py``'s ``_idea_record`` exactly: 0.0 credits (no
    script to price), ``story_json`` NULL, ``approved`` None until the
    operator picks. Developing the pick into a StoryScript is out of this
    ticket's scope (PRD "Out of Scope": everything downstream of the pick).
    """
    return AnglePitchRecord(
        trending_event_id=event_id,
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


def _print_slate(slate: ExilusSlate) -> None:
    """Render the numbered Exilus idea slate to stdout for the human to pick from."""
    print("\n" + "=" * 70)
    print(f"EXILUS SLATE ({len(slate.ideas)} ideas)")
    print("=" * 70)
    for i, idea in enumerate(slate.ideas, start=1):
        print(f"\n[{i}] {idea.logline}")
        print(f"     camp:   {idea.target_camp}")
        print(f"     mode:   {idea.mode.value}")
        print(f"     moment: {idea.desired_moment}")
        print(f"     why:    {idea.why_it_lands}")
        if idea.legal_flag:
            print("     ⚠ LEGAL FLAG — depends on a real person / specific IP")


def run_exilus_pipeline(
    db,
    context_agent,
    specificity_llm,
    faction_reader,
    ideator,
    embedder,
    *,
    topic: str,
    refresh: bool,
    choice_provider: Callable[[], str] | None,
    output_dir,
    max_repair_rounds: int = _MAX_REPAIR_ROUNDS,
) -> dict | None:
    """Run the Exilus pipeline for one topic, present the slate, persist the pick.

    Pinning (PRD "Pinning semantics"): a topic with BOTH artifacts already
    stored (brief with every checked field verified, and a faction map) and
    ``refresh=False`` skips research/checker/faction entirely -- only
    ``ideator.generate`` runs, fed the stored brief/faction_map plus the
    topic's previously-shown idea loglines as a do-not-repeat list (AC4/AC5).
    A topic with a VERIFIED brief but no faction map yet (e.g. an operator
    corrected an UNVERIFIED brief via --import-artifacts after a halt --
    that only re-pins the brief, never the faction map) skips research/
    checker and resumes directly at faction-read, so the operator's
    correction is never discarded and research is never redundantly re-run
    for a brief that's already good. Any other case (brief missing or still
    carrying an UNVERIFIED field, or ``refresh=True``) runs the full
    research -> checker(+repair) -> faction chain and REPLACES the stored
    artifacts and fridge rows (AC1/AC6) -- there is no partial-refresh mode.

    UNVERIFIED halt (AC2): if the checker's bounded repair budget
    (``max_repair_rounds``) is exhausted with fields still failing,
    ``check_and_repair_brief`` has already persisted the stamped brief and
    whatever was gathered has already been indexed into the fridge (research
    is never thrown away, even on a halt); this function prints which fields
    halted and returns ``None`` immediately -- the faction reader and
    ideator are never called, and no slate is ever printed or offered to the
    operator.

    Args:
        db: An open SQLAlchemy session.
        context_agent: Anything with ``gather_brief(topic) -> (TopicBrief,
            ContextBundle, web_text, ContextAgentState)`` and
            ``reenter_with_query(state, action, query) -> ContextAgentState``
            (the real ``ContextAgent`` in production, a fake in tests).
        specificity_llm: The ``brief_checker`` seat's LLM wrapper (or a fake)
            -- fed straight through to ``check_and_repair_brief``.
        faction_reader: Anything with ``read(topic, reddit_text) ->
            FactionMap``.
        ideator: Anything with ``generate(brief, faction_map,
            prior_loglines=()) -> ExilusSlate``.
        embedder: Injected embedder for ``replace_topic_material`` (unused on
            a pinned re-roll, since the fridge isn't touched then).
        topic: The topic name -- also the pinning key (``ExilusTopicRecord
            .topic`` / ``TrendingEventRecord.headline``).
        refresh: When true, force a full research/checker/faction re-run and
            REPLACE stored state, regardless of what's already pinned.
        choice_provider: Zero-arg callable returning the operator's
            selection as a string -- ``"1"``..``"15"`` to approve that idea,
            anything else (blank, ``"s"``, an out-of-range number) to skip.
            May be ``None`` (treated as an automatic skip -- no slate is
            interactive without it).
        output_dir: Directory the handoff JSON is written into (created if
            absent).
        max_repair_rounds: Passed straight through to
            ``check_and_repair_brief`` (PRD default: 2).

    Returns:
        The handoff dict written to disk (also returned for convenience) when
        an idea is approved; ``None`` on an UNVERIFIED halt, a skip, or an
        invalid selection.
    """
    pinned_brief = load_topic_brief(topic, db)
    pinned_faction = load_faction_map(topic, db)
    # A brief only counts as ready to skip research on if EVERY checked field
    # is verified -- a brief the checker itself halted on (some fields
    # UNVERIFIED) must still trigger a fresh research/checker pass, same as a
    # brief that was never researched at all.
    brief_ready = pinned_brief is not None and all(
        getattr(pinned_brief, field).verified for field in _CHECKED_FIELDS
    )

    if brief_ready and pinned_faction is not None and not refresh:
        print(f"[pinned] reusing stored brief + faction map for {topic!r} (re-roll)")
        assert pinned_brief is not None and pinned_faction is not None  # brief_ready/pinned_faction guarantee this
        brief: TopicBrief = pinned_brief
        faction_map: FactionMap = pinned_faction
    elif brief_ready and not refresh:
        # A verified, pinned brief with no faction map yet -- typically an
        # operator corrected an UNVERIFIED brief via --import-artifacts after
        # a halt (which pins ONLY the brief; see this function's "Pinning
        # semantics"). Research/checker never re-run for a brief that's
        # already good -- resume straight at faction-read instead of
        # discarding the operator's correction and re-researching from
        # scratch. No prior research state exists for this resume, so
        # faction-read gets an empty reddit_text and 0.0 spent-so-far -- its
        # own below-floor top-up logic (FactionReader.read) is exactly the
        # mechanism built for "not enough gathered comment text yet".
        print(f"[pinned] brief verified for {topic!r}, resuming at faction-read...")
        assert pinned_brief is not None  # brief_ready guarantees this
        brief = pinned_brief
        print(f"[faction] reading audience camps for {topic!r}...")
        faction_map = faction_reader.read(topic, "")
        save_faction_map(topic, faction_map, db)
    else:
        print(f"[research] gathering context for {topic!r}...")
        brief, _bundle, web_text, state = context_agent.gather_brief(topic)

        outcome = check_and_repair_brief(
            topic, brief, state, context_agent, specificity_llm, db,
            max_repair_rounds=max_repair_rounds,
        )

        # Index whatever was gathered into the fridge BEFORE the halt check
        # below -- an UNVERIFIED halt must not throw away the research it
        # just spent budget gathering just because the checker never
        # cleared it (PRD's research-is-never-thrown-away premise).
        replace_topic_material(topic, web_text, state.reddit_text, embedder, db)

        if outcome.halted:
            print(
                f"\n[HALT] TopicBrief for {topic!r} still has UNVERIFIED fields "
                f"after {outcome.rounds_used} repair round(s):"
            )
            for field in _CHECKED_FIELDS:
                if not getattr(outcome.brief, field).verified:
                    print(f"  - {field}")
            print(
                "Persisted as-is — inspect/correct the brief (--dump-artifacts / "
                "--import-artifacts) or re-run with --refresh once the source "
                "material improves. Faction read and ideation were NOT run."
            )
            return None

        brief = outcome.brief
        save_topic_brief(topic, brief, db)

        print(f"[faction] reading audience camps for {topic!r}...")
        faction_map = faction_reader.read(
            topic, state.reddit_text, spent_so_far=state.apify_cost_estimate
        )
        save_faction_map(topic, faction_map, db)

    event_record = _find_or_create_event(db, topic)
    prior_loglines = _prior_loglines(db, event_record.id)

    print(f"[ideation] generating slate for {topic!r}...")
    slate = ideator.generate(brief, faction_map, prior_loglines=prior_loglines)

    _print_slate(slate)

    pitch_records = [_idea_record(event_record.id, idea) for idea in slate.ideas]
    for pitch_record in pitch_records:
        db.add(pitch_record)
    db.flush()

    choice = choice_provider().strip().lower() if choice_provider else "s"

    if (
        choice in ("s", "skip", "", "q")
        or not choice.isdigit()
        or not (1 <= int(choice) <= len(pitch_records))
    ):
        db.commit()
        print(f"\nSkipped/invalid selection {choice!r} — slate saved, none approved.")
        return None

    index = int(choice) - 1
    chosen_record = pitch_records[index]
    chosen_idea = slate.ideas[index]

    chosen_record.approved = True
    chosen_record.approved_at = datetime.now(timezone.utc)
    db.flush()

    handoff = {
        "pitch_id": chosen_record.id,
        "logline": chosen_record.take,
        "mode": chosen_record.mode,
        "target_camp": chosen_idea.target_camp,
        "trendiness_score": event_record.trendiness_score,
    }
    db.commit()

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    handoff_path = out_dir / f"pitch_{handoff['pitch_id']}.json"
    handoff_path.write_text(json.dumps(handoff, indent=2), encoding="utf-8")

    print(f"\n✓ Approved idea [{choice}] -> {handoff_path}")
    return handoff


# ---------------------------------------------------------------------------
# --dump-artifacts / --import-artifacts (US22, resolved 2026-07-17: explicit
# two-step CLI edit flow, schema-validated on import, no file-watching).
# ---------------------------------------------------------------------------


def dump_artifacts(topic: str, db, out_dir) -> tuple[Path | None, Path | None]:
    """Write ``topic``'s stored TopicBrief/FactionMap as editable JSON files.

    Either file is skipped (returned as ``None``) when that artifact hasn't
    been researched yet — dumping is read-only and never fabricates a
    missing artifact.

    Returns the (brief_path, faction_path) written, either possibly ``None``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = _topic_slug(topic)

    brief_path = None
    brief = load_topic_brief(topic, db)
    if brief is not None:
        brief_path = out_dir / f"{slug}_brief.json"
        brief_path.write_text(
            json.dumps(brief.model_dump(mode="json"), indent=2), encoding="utf-8"
        )

    faction_path = None
    faction_map = load_faction_map(topic, db)
    if faction_map is not None:
        faction_path = out_dir / f"{slug}_faction.json"
        faction_path.write_text(
            json.dumps(faction_map.model_dump(mode="json"), indent=2), encoding="utf-8"
        )

    return brief_path, faction_path


def import_artifacts(topic: str, db, out_dir) -> tuple[bool, bool]:
    """Read back ``topic``'s dumped JSON files, validate, and re-pin (REPLACE).

    Looks for the exact filenames ``dump_artifacts`` writes
    (``<slug>_brief.json`` / ``<slug>_faction.json``) under ``out_dir``; a
    missing file is skipped (not an error — the operator may only have
    edited one artifact). Validation runs through the real Pydantic schemas
    (``TopicBrief.model_validate`` / ``FactionMap.model_validate``), so a
    hand-edit that breaks the schema raises before anything is persisted.

    Returns (brief_imported, faction_imported) booleans.
    """
    out_dir = Path(out_dir)
    slug = _topic_slug(topic)

    brief_imported = False
    brief_path = out_dir / f"{slug}_brief.json"
    if brief_path.exists():
        brief = TopicBrief.model_validate(json.loads(brief_path.read_text(encoding="utf-8")))
        save_topic_brief(topic, brief, db)
        brief_imported = True

    faction_imported = False
    faction_path = out_dir / f"{slug}_faction.json"
    if faction_path.exists():
        faction_map = FactionMap.model_validate(
            json.loads(faction_path.read_text(encoding="utf-8"))
        )
        save_faction_map(topic, faction_map, db)
        faction_imported = True

    return brief_imported, faction_imported


# ---------------------------------------------------------------------------
# Production wiring (real components). Not exercised by the unit tests.
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI args, build the real pipeline, and run the approval loop."""
    from dotenv import load_dotenv

    load_dotenv("config/.env")

    # Same Windows-console UTF-8 fix as pitch_angles.py — the slate prints
    # Unicode glyphs (⚠, ═, em-dashes) that raise UnicodeEncodeError on the
    # cp1252 default.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    parser = argparse.ArgumentParser(description="Exilus topic-to-slate front-end.")
    parser.add_argument("--topic", required=True, help="Any named subject (character, show, game, arc).")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force a full research/checker/faction re-run, REPLACING any "
        "stored brief, faction map, and fridge rows for this topic.",
    )
    parser.add_argument(
        "--choice",
        default=None,
        help="Non-interactive selection ('1'..'15' or blank/'s' to skip) — "
        "skips the input() prompt. When omitted, prompts interactively.",
    )
    parser.add_argument(
        "--dump-artifacts",
        action="store_true",
        help="Write this topic's stored brief + faction map as editable JSON "
        "files under --output-dir, then exit (no pipeline run).",
    )
    parser.add_argument(
        "--import-artifacts",
        action="store_true",
        help="Read back this topic's dumped JSON files under --output-dir, "
        "validate them, and re-pin (REPLACE) the stored artifacts, then exit "
        "(no pipeline run).",
    )
    parser.add_argument("--output-dir", default="output/pitches")
    args = parser.parse_args()

    if args.dump_artifacts and args.import_artifacts:
        parser.error("--dump-artifacts and --import-artifacts are mutually exclusive.")

    from src.database import SessionLocal

    if args.dump_artifacts or args.import_artifacts:
        db = SessionLocal()
        try:
            if args.dump_artifacts:
                brief_path, faction_path = dump_artifacts(args.topic, db, args.output_dir)
                print(f"[dump] brief -> {brief_path or '(none stored yet)'}")
                print(f"[dump] faction map -> {faction_path or '(none stored yet)'}")
            else:
                brief_ok, faction_ok = import_artifacts(args.topic, db, args.output_dir)
                print(f"[import] brief re-pinned: {brief_ok}")
                print(f"[import] faction map re-pinned: {faction_ok}")
        finally:
            db.close()
        return

    from src.monitor.context_agent import ContextAgent
    from src.monitor.faction_reader import FactionReader
    from src.monitor.ideation import Ideator
    from src.providers.llm.factory import llm_for_seat
    from src.rag.embedder import BgeM3Embedder

    context_agent = ContextAgent(llm=llm_for_seat("context_agent"))
    specificity_llm = llm_for_seat("brief_checker")
    embedder = BgeM3Embedder()
    faction_reader = FactionReader(llm=llm_for_seat("faction_reader"))
    ideator = Ideator(llm=llm_for_seat("ideator"), embedder=embedder)

    db = SessionLocal()
    try:
        run_exilus_pipeline(
            db,
            context_agent,
            specificity_llm,
            faction_reader,
            ideator,
            embedder,
            topic=args.topic,
            refresh=args.refresh,
            choice_provider=(
                (lambda: args.choice)
                if args.choice is not None
                else (lambda: input("\nPick an idea [#/s]: "))
            ),
            output_dir=args.output_dir,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
