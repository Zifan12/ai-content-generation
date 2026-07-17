"""Repair-repitch ONE stored AnglePitchRecord with explicit failure notes.

Unlike scripts/repitch_event.py (fresh slate from the parent event — new gap,
new ideas), this drives story_architect.repair() on the STORED script itself
(slice ①: the architect owns story repair now — the pitcher has no beats to
repair): same gap, same desired moment, same cast — only the story shape
changes. The idea the architect repairs against comes from the row's
idea_json when present, else it is reconstructed from the stored script's own
idea fields (pre-slice rows have no idea_json).

The repaired script is judged by the (upgraded, 10-dim) craft gate + dialogue
floor and persisted as a NEW AnglePitchRecord on the same parent event, with
location_slug copied from the source row so smoke_content_writer --pitch-id
works unchanged. The source row is never modified.

USAGE:
    uv run python scripts/repitch_pitch.py --pitch-id 43
    uv run python scripts/repitch_pitch.py --pitch-id 43 --notes "custom notes"

GapAnalysis note: evidence_quotes/reasoning are not persisted on
TrendingEventRecord (only dominant_emotion/audience_want are), so the
reconstructed gap carries empty quotes and a provenance note as reasoning —
weaker grounding than a live run, acceptable for a repair whose notes carry
the actual instruction.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv("config/.env")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

from src.database import SessionLocal  # noqa: E402
from src.generation.story_architect import (  # noqa: E402
    StoryArchitect,
    estimate_script_credits,
)
from src.models.angle_pitch import AnglePitchRecord  # noqa: E402
from src.models.trending_event import TrendingEventRecord  # noqa: E402
from src.monitor.schemas import (  # noqa: E402
    ContextBundle,
    GapAnalysis,
    IdeaPitch,
    StoryScript,
    TrendingEvent,
)
from src.monitor.story_craft_gate import StoryCraftGate  # noqa: E402
from src.monitor.voice_profiles import (  # noqa: E402
    check_dialogue_floor,
    format_cast_voices,
    load_cast_profiles,
)
from src.providers.llm.factory import llm_for_seat  # noqa: E402

# Default failure notes = the four sequence-craft rules (plan 2026-07-12,
# sources in config/render_rules.yaml sequence_craft). Scene Space is named
# concretely for pitch 43; --notes overrides for any other pitch.
DEFAULT_NOTES = (
    "1. ONE SCENE SPACE: the entire story must happen in Elfaria's bedroom plus "
    "at most its doorway (one visible threshold, crossed at most once as part of "
    "the action). No corridor, no hallway, no second room — nothing beyond the "
    "doorway's sightline exists. "
    "2. ONE ACTION PER BEAT: each beat stages exactly one physical action big "
    "enough to read in ~3 seconds — never several micro-motions in one beat. "
    "3. CHAIN THE BEATS: each beat's action begins exactly where the previous "
    "beat's action ended (end-state = start-state). "
    "4. AIR: the payoff beat gets the most time of any beat; keep the total story "
    "tellable in 10-15 seconds."
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair-repitch one stored pitch.")
    parser.add_argument("--pitch-id", type=int, required=True)
    parser.add_argument(
        "--notes",
        default=DEFAULT_NOTES,
        help="Failure notes fed to repitch(). Default: the four sequence-craft rules.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        source = db.get(AnglePitchRecord, args.pitch_id)
        if source is None or source.story_json is None:
            raise SystemExit(f"No AnglePitchRecord with story_json at id={args.pitch_id}.")
        event_record = db.get(TrendingEventRecord, source.trending_event_id)
        if event_record is None:
            raise SystemExit(f"Parent event {source.trending_event_id} missing.")

        failed_script = StoryScript.model_validate(source.story_json)
        # The idea the repair holds constant: stored idea_json when the row is
        # post-slice-①, else reconstructed from the script's own code-copied
        # idea fields (identical values by construction).
        idea = (
            IdeaPitch.model_validate(source.idea_json)
            if source.idea_json is not None
            else IdeaPitch(
                logline=failed_script.logline,
                mode=failed_script.mode,
                characters=failed_script.characters,
                desired_moment=failed_script.desired_moment,
                why_it_lands=failed_script.why_it_lands,
                legal_flag=failed_script.legal_flag,
            )
        )
        event = TrendingEvent(
            headline=event_record.headline,
            subreddit=event_record.source,
            url=event_record.url or "",
            reaction_sample=event_record.reaction_sample,
            trendiness_score=event_record.trendiness_score,
            virality_window_hours=event_record.virality_window_hours,
            raw_source_data={},
            origin="manual",
        )
        gap = GapAnalysis(
            dominant_emotion=event_record.dominant_emotion or "unknown",
            audience_want=event_record.audience_want or failed_script.desired_moment,
            evidence_quotes=[],
            reasoning="(reconstructed from stored event; quotes not persisted)",
        )
        bundle = (
            ContextBundle.model_validate(event_record.context_bundle)
            if event_record.context_bundle is not None
            else None
        )

        cast_profiles = load_cast_profiles()
        cast_voices = format_cast_voices(cast_profiles)

        architect = StoryArchitect(llm=llm_for_seat("story_architect"))
        gate = StoryCraftGate(llm=llm_for_seat("story_craft_gate"))

        print(f"[repitch] pitch {args.pitch_id}: {failed_script.logline}")
        print(f"[repitch] notes: {args.notes[:120]}...")
        repaired = architect.repair(
            idea, event, gap, failed_script, args.notes, bundle,
            cast_voices=cast_voices,
        )

        verdict = gate.evaluate(repaired, event, gap)
        floor_ok, floor_reason = check_dialogue_floor(repaired, set(cast_profiles))

        print(f"\n[repaired] {repaired.logline}")
        print(f"[repaired] scene_setting: {repaired.scene_setting}")
        for i, beat in enumerate(repaired.beats):
            line = f"  beat {i} [{beat.role.value}] {beat.visual_line}"
            if beat.dialogue_line:
                line += f'  || {beat.speaker}: "{beat.dialogue_line}"'
            print(line)
        print(f"\n[gate] passes={verdict.passes} floor={floor_ok}")
        if verdict.failure_notes:
            print(f"[gate] failure_notes: {verdict.failure_notes}")
        if floor_reason:
            print(f"[floor] {floor_reason}")

        record = AnglePitchRecord(
            trending_event_id=source.trending_event_id,
            take=repaired.logline,
            estimated_cost_credits=estimate_script_credits(repaired),
            gap_satisfaction_rationale=repaired.why_it_lands,
            legal_flag=repaired.legal_flag,
            approved=None,
            idea_json=idea.model_dump(mode="json"),
            story_json=repaired.model_dump(mode="json"),
            mode=repaired.mode.value,
            craft_verdict_json=verdict.model_dump(mode="json"),
            killed_by_gate=not (verdict.passes and floor_ok),
            location_slug=source.location_slug,
        )
        db.add(record)
        db.commit()
        print(f"\n[persisted] new pitch id={record.id} (location_slug={record.location_slug})")
        print(
            f"Next: uv run python scripts/smoke_content_writer.py "
            f"--pitch-id {record.id} --dry-run"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
