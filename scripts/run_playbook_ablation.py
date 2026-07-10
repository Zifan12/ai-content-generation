"""
Ablation: does the mode playbook over-constrain the StoryPitcher toward sameness?

Controlled experiment, blind human read. For each fixture (event, gap), run the
pitcher TWICE on the SAME gap — arm WITH the playbook (production default) vs arm
WITHOUT it (``playbook_block = ""``). Everything else held fixed, so the single
changed variable is the playbook. Both slates are written to a blinded file
(arm labels hidden, order shuffled per event); the true mapping goes to a
separate key file to open only AFTER judging.

What to look for when reading the blinded output (the "and look" of the ablation):
  - RANGE:  are the no-playbook pitches more varied / less samey?
  - CRAFT:  are they worse built (no clear turn, unearned payoff, off-format)?
Three verdicts: more-varied-AND-still-crafted (drop the playbook), more-varied-
but-sloppier (playbook holds the craft floor, keep it), or not-more-varied (the
playbook wasn't the thing flattening output — look at the 2-mode taxonomy).

Structural cousin of scripts/run_pitch_ablation.py (same fixture-load + two-arm
pitcher shape), but the changed variable is the WHOLE playbook (not just the
worked example), and scoring is a blind human read (not the GroundednessJudge).

Reads the fixture as UTF-8 and strips the stale ``virality_window_hours`` key the
current GapAnalysis schema no longer allows (fixture predates that schema change).

LIVE SPEND: runs the real pitcher twice per fixture event (deepseek). State the
cost ceiling before running.
"""

import argparse
import json
import logging
import random
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

from src.monitor.schemas import GapAnalysis, StoryPitchSlate, TrendingEvent  # noqa: E402
from src.monitor.story_pitcher import StoryPitcher  # noqa: E402
from src.providers.llm.factory import llm_for_seat  # noqa: E402
from src.rag.embedder import BgeM3Embedder  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "data" / "golden" / "pitcher_groundedness_fixture_v1.json"
)
_OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "playbook_ablation"
_BLINDED_PATH = _OUT_DIR / "ab_blinded.md"
_KEY_PATH = _OUT_DIR / "ab_key.md"


def _load_pairs(fixture: Path, limit: int | None) -> list[tuple[TrendingEvent, GapAnalysis]]:
    """Rebuild (event, gap) pairs from the fixture (mirrors run_pitch_ablation).

    Reads UTF-8 and drops the stale ``virality_window_hours`` key from each gap
    (the fixture predates its removal from GapAnalysis, which now forbids extras).
    Event metadata beyond the persisted fields is synthesized — the fixture is a
    scoring input, not a live scrape.
    """
    raw_entries = json.loads(fixture.read_text(encoding="utf-8"))[:limit]
    pairs: list[tuple[TrendingEvent, GapAnalysis]] = []
    for entry in raw_entries:
        event = TrendingEvent.model_validate(
            {
                **{
                    k: entry[k]
                    for k in ("headline", "reaction_sample", "trendiness_score",
                              "virality_window_hours")
                },
                "subreddit": "",
                "url": "",
                "raw_source_data": {},
                "origin": "manual",
            }
        )
        gap_data = {k: v for k, v in entry["gap"].items() if k != "virality_window_hours"}
        pairs.append((event, GapAnalysis.model_validate(gap_data)))
    return pairs


def _format_slate(slate: StoryPitchSlate) -> str:
    """Render a slate's pitches as readable markdown (logline + beats), no arm label."""
    parts: list[str] = []
    for i, pitch in enumerate(slate.pitches, start=1):
        beats = "\n".join(f"    {b.role.value}: {b.visual_line}" for b in pitch.beats)
        parts.append(
            f"- **Pitch {i}** — {pitch.logline}\n"
            f"  - mode: {pitch.mode.value}\n"
            f"  - desired_moment: {pitch.desired_moment}\n"
            f"  - beats:\n{beats}"
        )
    return "\n".join(parts)


def main() -> None:
    """Run the playbook ablation over the fixture and write blinded + key files."""
    parser = argparse.ArgumentParser(description="Playbook ablation (blind human read).")
    parser.add_argument("--fixture", type=Path, default=_FIXTURE_PATH)
    parser.add_argument("--limit", type=int, default=None, help="cap events (cost control)")
    args = parser.parse_args()

    pairs = _load_pairs(args.fixture, args.limit)
    if not pairs:
        log.error("No fixture pairs loaded from %s", args.fixture)
        raise SystemExit(1)
    log.info("Playbook ablation over %d events (2 arms each)", len(pairs))

    # One embedder shared by both pitchers (loading BgeM3 twice just doubles VRAM).
    # Arm "with" keeps the production playbook; arm "without" strips it entirely —
    # the single changed variable.
    embedder = BgeM3Embedder()
    pitcher_with = StoryPitcher(llm=llm_for_seat("story_pitcher"), embedder=embedder)
    pitcher_without = StoryPitcher(llm=llm_for_seat("story_pitcher"), embedder=embedder)
    pitcher_without.playbook_block = ""

    blinded_blocks: list[str] = []
    key_blocks: list[str] = []

    for event, gap in pairs:
        # Per-event isolation (mirrors run_pitch_ablation): a failed pitch drops
        # THIS event and keeps the rest.
        try:
            slate_with = pitcher_with.pitch(event, gap)
            slate_without = pitcher_without.pitch(event, gap)
        except Exception as e:
            log.warning("Skipped event %r: %s", event.headline, e)
            continue

        arms = [("with-playbook", slate_with), ("without-playbook", slate_without)]
        random.shuffle(arms)
        blinded_blocks.append(
            f"## Event: {event.headline}\n\n"
            f"### Option 1\n{_format_slate(arms[0][1])}\n\n"
            f"### Option 2\n{_format_slate(arms[1][1])}\n"
        )
        key_blocks.append(
            f"## Event: {event.headline}\n"
            f"- Option 1 = {arms[0][0]}\n"
            f"- Option 2 = {arms[1][0]}\n"
        )

    if not blinded_blocks:
        log.error("No events produced pitches — every event failed")
        raise SystemExit(1)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _BLINDED_PATH.write_text("\n".join(blinded_blocks), encoding="utf-8")
    _KEY_PATH.write_text("\n".join(key_blocks), encoding="utf-8")
    log.info("Wrote blinded comparison -> %s", _BLINDED_PATH)
    log.info("Wrote answer key (open AFTER judging) -> %s", _KEY_PATH)


if __name__ == "__main__":
    main()
