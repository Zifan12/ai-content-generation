"""
Judge-fixture wrapper + loader for the negative-control floor probe (P3 eval).

A "judge fixture" is one saved test input for the writer-judge: the two things
the judge needs to score — a premise (the prompt) and a ContentPackage (the
writer's output) — bundled into one JSONL row so they travel together. This is
the honest unit: the judge's input IS the (premise, package) pair, so storing
them apart (premise paired against a hardcoded list by index) is the order-pairing
fragility this module exists to avoid.

JudgeFixture is the wrapper model; load_judge_fixtures reads a JSONL of them into
(premise, package) pairs. Both the `run_rubric_eval --fixtures` driver mode and the
gated floor test call the SAME loader, so they cannot disagree on the fixture shape.
Because the nested package is validated when the wrapper is built, a row whose
package breaks ContentPackage's chain contract fails at LOAD time, before any paid
Opus call is ever made.
"""

from pathlib import Path
from pydantic import BaseModel
from src.schemas.generation import ContentPackage


class JudgeFixture(BaseModel):
    premise: str
    package: ContentPackage


def load_judge_fixtures(path: Path) -> list[tuple[str, ContentPackage]]:
    """
    Read a judge-fixture JSONL (one JudgeFixture per line) into (premise, package)
    pairs, in file order. Blank lines are skipped. Each line is validated via the
    JudgeFixture wrapper, so a malformed row — or one whose nested package breaks the
    chain contract — raises a Pydantic ValidationError HERE, before any paid Opus call.

    The single source of truth for "what a judge fixture is": both the
    run_rubric_eval --fixtures driver mode and the gated floor test call this loader,
    so they cannot disagree on the fixture shape.
    """
    pairs: list[tuple[str, ContentPackage]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            fixture = JudgeFixture.model_validate_json(line)
            pairs.append((fixture.premise, fixture.package))
    return pairs