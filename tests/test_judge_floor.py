"""
Negative-control FLOOR test for the v1 writer-judge (P3 eval).

The permanent regression lock that the manual `run_rubric_eval --fixtures` run does
NOT give you: it loads the deliberately-bad static/splintered fixture, judges it
(one PAID Opus call), and asserts the judge scores LOW on exactly the two dimensions
the fixture sabotages — development and vividness. If a future rubric edit ever makes
the judge lenient enough that the empty package scores 3+ on those dims, THIS test
fails loud. (premise_fidelity and device_execution are intentionally NOT asserted: the
fixture does not deliberately sabotage them, so constraining them would invite flaky
failures on untargeted dimensions.)

GATING: this is a PAID Opus call (~$0.12). It is SKIPPED unless BOTH:
  - RUN_PAID_EVALS=1 is set (explicit opt-in to spend), AND
  - ANTHROPIC_API_KEY is set (so a fresh clone / CI without secrets skips, not errors).
So the default `pytest` run stays free, offline, and fast — this test only fires when
you deliberately ask for the paid tier.

DETERMINISM: Opus has no temperature knob (removed on 4.7+), so scores are not bit-
identical run to run. A <= 2 band on a deliberately-empty package is robust (nowhere
near the 2<->3 boundary). If it ever wobbles 2<->3 on this fixture, that is SIGNAL,
not noise: either the fixture is not bad enough, or the anchor is too lenient.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Load config/.env BEFORE _GATE is computed below, so ANTHROPIC_API_KEY is present in
# the environment when the gate reads it. pytest (unlike the run_rubric_eval driver)
# does not load .env on its own, so without this the key half of the gate is always
# False and the test silently skips even with RUN_PAID_EVALS=1.
load_dotenv("config/.env")

from src.evals.judge_fixture import load_judge_fixtures  # noqa: E402
from src.evals.writer_judge import WriterJudge  # noqa: E402

FIXTURE_PATH = Path("data/golden/writer_floor_static.jsonl")

# Both gates must be open: opt-in to paid runs AND a key present.
_GATE = os.environ.get("RUN_PAID_EVALS") == "1" and bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(
    not _GATE,
    reason="paid Opus call; set RUN_PAID_EVALS=1 (and ANTHROPIC_API_KEY) to run",
)
def test_floor_static_package_scores_low():
  pairs = load_judge_fixtures(FIXTURE_PATH)
  verdict = WriterJudge().judge(pairs[0][0], pairs[0][1]) 
  dimension_map = {ds.dimension: ds.score for ds in verdict.scores}

  assert dimension_map["development"] <=2 
  assert dimension_map["vividness"] <= 2

