"""
Phase-0 A/B: does the discarded raw web text let the pitcher reach a detail the
compressed summary drops? (web-research fridge, plan 2026-07-09.)

Controlled counterfactual, blind human read (n~2). For each topic:
  arm A = pitch off today's bundle (summary + key_moments only)
  arm B = pitch off the SAME bundle PLUS the raw web text that _finalize discards
Everything else is held fixed, so the single changed variable is "does the
pitcher see the raw web material." Both arms' pitches are written to a blinded
file (arm labels hidden, order shuffled per topic) so a human can judge which is
more grounded WITHOUT knowing which arm produced it; the true mapping is written
to a SEPARATE key file to open only AFTER judging.

Structural cousin of scripts/run_pitch_ablation.py (same two-arm-per-input
shape), but: the changed variable is bundle richness (not the playbook example),
inputs are LIVE topic runs (not a static fixture), and scoring is a blind human
read (not the GroundednessJudge — deliberately omitted; add it later only if a
quantitative backstop is wanted, per the spec's "optional at n=2" note).

LIVE SPEND: each topic runs the real ContextAgent (Apify + Tavily + Firecrawl +
LLM) once, gap_agent once, and the pitcher TWICE. State the cost ceiling before
running. Sets AICG_PHASE0_DUMP=1 so the raw web text lands on disk for arm B.
"""

import argparse
import logging
import os
import random
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

from src.monitor.context_agent import ContextAgent, phase0_dump_path  # noqa: E402
from src.monitor.gap_agent import GapAgent  # noqa: E402
from src.monitor.schemas import ContextBundle, StoryPitchSlate  # noqa: E402
from src.monitor.story_pitcher import StoryPitcher  # noqa: E402
from src.providers.llm.factory import llm_for_seat  # noqa: E402
from src.rag.embedder import BgeM3Embedder  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_OUT_DIR = Path(__file__).resolve().parent.parent / "output" / "phase0"
_BLINDED_PATH = _OUT_DIR / "ab_blinded.md"
_KEY_PATH = _OUT_DIR / "ab_key.md"


def _augment_bundle_with_raw(bundle: ContextBundle, raw_web_text: str) -> ContextBundle:
    """Build arm B's bundle: the same research bundle, plus the raw web text.

    Arm B must be a clean "summary + raw" (NOT "raw replacing summary"), so the
    raw web material is the single changed variable vs arm A. The pitcher only
    ever renders a bundle through ``ContextBundle.to_context_block()``, which
    emits ``summary`` verbatim — so appending the raw text to a COPY of the
    summary is the least-invasive way to make the pitcher see BOTH: arm A keeps
    the original bundle (summary only), while arm B's context block shows the
    same summary followed by a clearly-delimited raw block. ``model_copy``
    returns a new object, leaving the ``bundle`` arm A reuses untouched.
    """
    augmented_summary = (
        f"{bundle.summary}\n\n"
        f"[RAW WEB RESEARCH — uncompressed, for grounding]\n{raw_web_text}"
    )
    return bundle.model_copy(update={"summary": augmented_summary})


def _format_slate(slate: StoryPitchSlate) -> str:
    """Render a pitch slate as readable markdown for the blinded comparison file.

    One block per pitch: logline, desired_moment, why_it_lands, and the ordered
    beats (role + visual line). Enough for a human to judge groundedness; no arm
    label is emitted here (blinding lives in the caller).
    """
    parts: list[str] = []
    for i, pitch in enumerate(slate.pitches, start=1):
        beats = "\n".join(
            f"    {b.role.value}: {b.visual_line}" for b in pitch.beats
        )
        parts.append(
            f"- **Pitch {i}** — {pitch.logline}\n"
            f"  - desired_moment: {pitch.desired_moment}\n"
            f"  - why_it_lands: {pitch.why_it_lands}\n"
            f"  - beats:\n{beats}"
        )
    return "\n".join(parts)


def main() -> None:
    """
    Run the Phase-0 fridge A/B over one or more topics and write a blinded
    comparison + a separate answer key.

    Each ``--topic`` is gathered live once (ContextAgent, with the raw-web dump
    flag set), analyzed once (gap_agent), then pitched twice — arm A on the plain
    bundle, arm B on the raw-augmented bundle. Per-topic failures are isolated:
    a failed gather/gap/pitch drops THAT topic and keeps the rest (mirrors
    run_pitch_ablation.py). Writes ab_blinded.md (shuffled, unlabeled) and
    ab_key.md (the true arm order) under output/phase0/.
    """
    parser = argparse.ArgumentParser(description="Phase-0 fridge A/B (blind human read).")
    parser.add_argument(
        "--topic", action="append", required=True,
        help="a topic to A/B; pass 2+ times for multiple topics",
    )
    args = parser.parse_args()

    # Make ContextAgent dump each topic's raw web text to phase0_dump_path so
    # arm B can read it back. Set for the whole process before any gather().
    os.environ["AICG_PHASE0_DUMP"] = "1"

    agent = ContextAgent(llm=llm_for_seat("context_agent"))
    gap_agent = GapAgent(llm=llm_for_seat("gap_agent"))
    pitcher = StoryPitcher(llm=llm_for_seat("story_pitcher"), embedder=BgeM3Embedder())

    blinded_blocks: list[str] = []
    key_blocks: list[str] = []

    for topic in args.topic:
        # Per-topic isolation: a failed gather/gap/pitch drops THIS topic and
        # keeps whatever earlier topics already produced (mirrors
        # run_pitch_ablation.py's per-event try).
        try:
            event, bundle = agent.gather(topic)
            raw_web_text = phase0_dump_path(topic).read_text(encoding="utf-8")
            gap = gap_agent.analyze(event, bundle)

            slate_a = pitcher.pitch(event, gap, bundle)
            slate_b = pitcher.pitch(event, gap, _augment_bundle_with_raw(bundle, raw_web_text))
        except Exception as e:
            log.warning("Skipped topic %r: %s", topic, e)
            continue

        # Blind: shuffle which arm is shown as Option 1 vs Option 2, so the
        # reader cannot infer the arm from position. Record the true mapping in
        # the separate key file to open only after judging.
        arms = [("A", slate_a), ("B", slate_b)]
        random.shuffle(arms)
        blinded_blocks.append(
            f"## Topic: {topic}\n\n"
            f"### Option 1\n{_format_slate(arms[0][1])}\n\n"
            f"### Option 2\n{_format_slate(arms[1][1])}\n"
        )
        key_blocks.append(
            f"## Topic: {topic}\n"
            f"- Option 1 = arm {arms[0][0]}\n"
            f"- Option 2 = arm {arms[1][0]}\n"
            f"  (arm A = summary only; arm B = summary + raw web text)\n"
        )

    if not blinded_blocks:
        log.error("No topics produced a result — every topic failed")
        raise SystemExit(1)

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _BLINDED_PATH.write_text("\n".join(blinded_blocks), encoding="utf-8")
    _KEY_PATH.write_text("\n".join(key_blocks), encoding="utf-8")
    log.info("Wrote blinded comparison -> %s", _BLINDED_PATH)
    log.info("Wrote answer key (open AFTER judging) -> %s", _KEY_PATH)


if __name__ == "__main__":
    main()
