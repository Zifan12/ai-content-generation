"""Live negative-control test for StoryCraftGate (Task 8, Step 1).

Feeds the schema-valid-but-craft-dead ``BAD_TABLEAU_PITCH`` through the gate
with the REAL AnthropicLLM (Sonnet) and asserts the judge kills it. This is
the writer-judge "everything scores 5.00" lesson made executable: if the real
judge passes a pitch deliberately built with no turn, no earned payoff, and
labeled emotion, the judge prompt needs iteration BEFORE any paid pitch run.

Cost: one Sonnet call (~small cents). Guarded per the option-2 decision
(2026-07-02): the guard lives IN this file, not in shared config — the test
skips itself unless RUN_LIVE=1 is set in the environment. Run with:

    RUN_LIVE=1 uv run pytest tests/monitor/test_story_craft_gate_live.py -q
    (PowerShell: $env:RUN_LIVE="1"; uv run pytest tests/monitor/test_story_craft_gate_live.py -q)

Unlike the FakeLLM unit tests in ``test_story_craft_gate.py`` (which pair the
Homelander pitch with an unrelated dragon event — irrelevant when the LLM is
fake), this live test gives the real judge a COHERENT context: an event and
gap analysis about the same Homelander finale the fixture pitch responds to,
so the verdict reflects the pitch's craft, not a confusing event mismatch.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from src.monitor.schemas import GapAnalysis, TrendingEvent
from src.monitor.story_craft_gate import StoryCraftGate
from src.providers.llm.factory import llm_for_seat
from src.providers.llm.openrouter_llm import OpenRouterLLM
from tests.monitor.fixtures.bad_tableau_pitch import BAD_TABLEAU_PITCH

# Load the API key explicitly rather than relying on src.database's import-time
# side effect (which only fires when DATABASE_URL is unset).
_ENV_PATH = Path(__file__).resolve().parents[2] / "config" / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=False)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("RUN_LIVE") != "1",
        reason="paid live-API test; set RUN_LIVE=1 to run",
    ),
]

# Event + gap coherent with BAD_TABLEAU_PITCH (Homelander / The Boys finale).
LIVE_EVENT = TrendingEvent(
    headline="The Boys series finale ends without the Homelander rampage fans expected",
    subreddit="TheBoys",
    url="https://reddit.com/r/TheBoys/comments/finale_thread",
    reaction_sample=(
        "Top comment: 'All that buildup and we never see him actually snap. Robbed.' "
        "Reply: 'Eight seasons of teasing the rampage and they cut to black.'"
    ),
    trendiness_score=0.95,
    virality_window_hours=24.0,
    raw_source_data={},
    origin="scraped",
)

LIVE_GAP = GapAnalysis(
    dominant_emotion="frustration",
    audience_want="to finally see Homelander fully cut loose in the rampage the finale teased",
    evidence_quotes=[
        "All that buildup and we never see him actually snap. Robbed.",
        "Eight seasons of teasing the rampage and they cut to black.",
    ],
    virality_window_hours=24.0,
    reasoning="The finale promised an explosion of violence and withheld it; fans feel denied the payoff.",
)


def test_real_judge_kills_bad_tableau_pitch():
    """The REAL Sonnet judge must fail the craft-dead fixture (passes is False).

    If this fails, the gate cannot discriminate — iterate the judge prompt
    before spending on a real --topic run.
    """
    # Default: judge with whatever model the story_craft_gate seat is
    # configured to run in production (providers.yaml) — the negative control
    # should always validate the REAL configured judge. LIVE_MODEL_OVERRIDE
    # lets the promotion protocol (spec 3.4) point the same control at a
    # candidate model via OpenRouter before flipping the YAML.
    override = os.environ.get("LIVE_MODEL_OVERRIDE")
    llm = OpenRouterLLM(model=override) if override else llm_for_seat("story_craft_gate")
    gate = StoryCraftGate(llm=llm)

    verdict = gate.evaluate(BAD_TABLEAU_PITCH, LIVE_EVENT, LIVE_GAP)

    # Surface the judge's reasoning either way (visible with `pytest -s` or on failure).
    print(f"\nverdict: {verdict.model_dump_json(indent=2)}")

    assert verdict.passes is False, (
        "StoryCraftGate passed the negative-control pitch — the judge is not "
        f"discriminating. Full verdict: {verdict.model_dump_json(indent=2)}"
    )
