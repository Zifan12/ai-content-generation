"""
Typed verdict schema for the v1 writer-judge (P3 eval).

The judge returns one PackageVerdict per scored ContentPackage; constraining the
score at the type boundary makes a hallucinated out-of-range value a parse error
rather than a silent bad number flowing into the scorecard.
"""

import yaml
from pydantic import BaseModel, Field
from src.providers.llm.anthropic_llm import AnthropicLLM
from src.evals.package_view import render_for_judge
from src.schemas.generation import ContentPackage

SYSTEM_PROMPT = """\
You are a strict quality judge for short-form AI video content packages.

You will receive:
- a <rubric> section (below) defining 4 scoring dimensions, each with a \
question and anchor sentences describing scores 1, 3, and 5
- one content package brief as the user message: a premise, a device with \
rationale, a mood anchor, and three chained segment blocks (segment 1 carries \
the only opening frame; later segments begin on the previous clip's final frame)

<instructions>
- Score the package on EVERY dimension in the rubric: an integer 1-5 plus a
  concrete reason citing specific text from the brief.
- Anchors define scores 1, 3, and 5; use 2 and 4 for cases that fall between
  adjacent anchors.
- Judge only what is in the brief. Do not reward fluent or vivid prose that
  ignores the premise or routes the premise to the wrong device.
- Use the dimension ids exactly as written in the rubric for the `dimension`
  field of each score entry.
</instructions>
"""

class DimensionScore(BaseModel):
    """One rubric dimension's score on one package: the dimension, its 1-5 Likert score, and the reason."""

    dimension: str
    score: int = Field(ge=1, le=5)
    reason: str = Field(max_length=500)


class PackageVerdict(BaseModel):
    """A judge's full verdict on one package — one DimensionScore per rubric dimension."""

    scores: list[DimensionScore]

class WriterJudge:
    def __init__(self, model: str = "claude-opus-4-8"):
        self.llm = AnthropicLLM(model=model)

        with open("config/writer_rubric_v1.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.dimensions = data["dimensions"]

        

    def judge(self, premise: str, package: ContentPackage) -> PackageVerdict:
        """
        Score one ContentPackage against the v1 rubric — the PAID Opus call.

        Renders the package brief (user message) and the rubric-bearing system
        prompt, then parses the response into a PackageVerdict (schema-validated
        server-side). max_tokens=2048 so a 4-reason verdict cannot truncate
        mid-JSON. No temperature: sampling params are removed on Opus 4.7+
        (400 if sent); score stability is checked empirically in calibration.
        """
        rubric = self._render_rubric()
        return self.llm.parse(
            prompt=render_for_judge(premise, package),
            response_model=PackageVerdict,
            system=f"{SYSTEM_PROMPT}\n<rubric>\n{rubric}\n</rubric>",
            max_tokens=2048,
        )


    def _render_rubric(self) -> str:
        """
        Flatten the loaded rubric dimensions into the judge-readable text block.

        One chunk per dimension: its id, the question, and the 1/3/5 anchor
        sentences. Pure (no LLM) — `judge` embeds this in the paid prompt.
        """
        chunks = []
        for dim in self.dimensions:
            chunks.append(
                f"## {dim['id']}\n"
                f"Question: {dim['question']}\n"
                f"Score 1: {dim['anchors'][1]}\n"
                f"Score 3: {dim['anchors'][3]}\n"
                f"Score 5: {dim['anchors'][5]}\n"
            )
        return "\n".join(chunks) 