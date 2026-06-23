import json
import pytest
from pydantic import ValidationError
from tests.helpers.content_package import baseline_package
from src.evals.judge_fixture import JudgeFixture, load_judge_fixtures

# PARKED behind the single-shot pivot (plan Task 7): judge-fixture round-trip +
# chain-contract tests built on the retired 3-shot schema (baseline_package, the
# now-deleted chain validator). Kept for a future vision judge; skipped so the
# suite stays green.
pytestmark = pytest.mark.skip(reason="judge fixtures parked behind single-shot pivot (plan Task 7)")


def test_round_trip(tmp_path):
    package = baseline_package()
    fixture = JudgeFixture(premise="test", package=package)
    path = tmp_path / "fixture.jsonl"
    path.write_text(fixture.model_dump_json())

    pairs = load_judge_fixtures(path)

    assert len(pairs) == 1
    assert pairs[0][0] == "test"
    assert pairs[0][1].device == package.device


def test_chain_break_fails_at_load(tmp_path):
    """
    A fixture row whose package breaks the chain contract (segment 2 carries a
    start_keyframe, which the inheriting segments must NOT) raises ValidationError
    at LOAD time — before any paid Opus call — not later when the judge runs.

    The bad row is built as a plain dict and json.dumps'd to disk, NOT via the
    JudgeFixture / ContentPackage models: constructing those would run the chain
    validator immediately and raise here in the test, before the row ever reached
    disk. We need invalid TEXT on disk so the LOADER is the thing that validates and
    raises — which is exactly the behavior under test.
    """
    pkg_dict = baseline_package().model_dump()
    pkg_dict["shots"][1]["start_keyframe"] = "illegal inherited-segment keyframe"
    row = {"premise": "test", "package": pkg_dict}

    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(row))

    with pytest.raises(ValidationError):
        load_judge_fixtures(path)