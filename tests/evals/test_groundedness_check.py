"""Unit tests for the groundedness scorer's ASSEMBLY and plumbing.

These tests mock the LLM (FakeLLM), so they deliberately CANNOT test the
judge's judgment quality — a mock returns whatever verdict we canned, so any
assertion about the *labels* would just be checking our own fixture. What a
mock CAN test is our own code: does `GroundednessJudge.judge()` correctly
assemble the evidence + pitch into the prompt it hands the LLM, and does it
survive the nullable/empty edge cases of the real schemas.

The judge's actual discrimination (does it score a generic pitch lower than a
grounded one?) is a property of the real model and lives in a separate live
calibration probe, NOT here.
"""

from src.evals.groundedness_check import (
    EvidenceItemVerdict,
    GroundednessJudge,
    GroundednessVerdict,
)
from src.monitor.schemas import (
    BeatRole,
    CharacterRef,
    ContentMode,
    GapAnalysis,
    ShotSize,
    StoryBeat,
    StoryPitch,
)
from tests.monitor.fixtures.bad_tableau_pitch import BAD_TABLEAU_PITCH


# --- fakes & fixtures ---------------------------------------------------------


class FakeLLM:
    """Stand-in for the real LLM: records the prompt/system it was handed and
    returns a verdict we choose. No network, no cost, deterministic — so any
    variation in what we assert is the judge's assembly, never model randomness.
    """

    def __init__(self, verdict: GroundednessVerdict) -> None:
        self._verdict = verdict
        self.last_prompt: str | None = None
        self.last_system: str | None = None

    def parse(self, prompt, response_model, system=None, max_tokens=1024):
        self.last_prompt = prompt
        self.last_system = system
        return self._verdict


def _canned_verdict() -> GroundednessVerdict:
    """A schema-valid verdict. Its label values are arbitrary — these plumbing
    tests never assert on them (that would just be testing this fixture)."""
    return GroundednessVerdict(
        reasoning="canned reasoning for plumbing tests",
        swap=False,
        swap_justification="canned",
        evidence_items=[
            EvidenceItemVerdict(
                evidence_quote="canned quote",
                label="grounded",
                pitch_span="canned span",
            )
        ],
    )


# A distinctive quote so an assertion can look for it verbatim in the prompt.
SAMPLE_QUOTE = "I wish we got to see it actually breathe fire."


def _sample_gap() -> GapAnalysis:
    """A gap carrying real evidence — used to check the evidence reaches the prompt."""
    return GapAnalysis(
        dominant_emotion="longing",
        audience_want="to see the dragon actually breathe fire",
        evidence_quotes=[SAMPLE_QUOTE],
        reasoning="The crowd was teased a payoff the footage never delivered.",
    )


def _empty_quotes_gap() -> GapAnalysis:
    """A gap with NO evidence_quotes (the schema allows an empty list) — used to
    check the prompt assembly does not crash when there are zero quotes to join."""
    return GapAnalysis(
        dominant_emotion="longing",
        audience_want="to see the dragon actually breathe fire",
        evidence_quotes=[],
        reasoning="No direct quotes were captured, only aggregate sentiment.",
    )


def _none_fields_pitch() -> StoryPitch:
    """A schema-valid pitch whose nullable fields are None: the middle beat has
    narration_line=None.
    Used to check the assembly's None-guards don't leak the literal string 'None'
    into the prompt.
    """
    return StoryPitch(
        logline="A dragon circles the tower at dawn.",
        mode=ContentMode.wish,
        characters=[
            CharacterRef(name="Dragon", ip_source="Original", needs_reference=False)
        ],
        desired_moment="Fans wanted to see the dragon finally breathe fire.",
        beats=[
            StoryBeat(
                role=BeatRole.establish,
                visual_line="The dragon glides in low over the rooftops.",
                narration_line="Dawn breaks over the city.",
                shot_size=ShotSize.establishing,
                characters_in_frame=["Dragon"],
                hero_moment=False,
            ),
            StoryBeat(
                role=BeatRole.build,
                visual_line="It banks toward the tower, wings flexing.",
                narration_line=None,  # the nullable branch under test
                shot_size=ShotSize.wide,
                characters_in_frame=["Dragon"],
                hero_moment=False,
            ),
            StoryBeat(
                role=BeatRole.payoff,
                visual_line="A jet of fire erupts across the skyline.",
                narration_line="Finally, the fire.",
                shot_size=ShotSize.close_up,
                characters_in_frame=["Dragon"],
                hero_moment=True,
            ),
        ],
        why_it_lands="The payoff the footage denied.",
        legal_flag=False,
    )



def test_evidence_appears_in_prompt():
    """The judge must actually put the gap's evidence into the prompt it sends —
    if it doesn't, the real judge would be scoring blind."""
    fake = FakeLLM(_canned_verdict())
    judge = GroundednessJudge(llm=fake)

    judge.judge(_sample_gap(), BAD_TABLEAU_PITCH)

    assert SAMPLE_QUOTE in fake.last_prompt


def test_empty_quotes_gap_builds_ok():
    """A gap with zero evidence_quotes must not break prompt assembly."""
    fake = FakeLLM(_canned_verdict())
    judge = GroundednessJudge(llm=fake)

    judge.judge(_empty_quotes_gap(), BAD_TABLEAU_PITCH)

    assert fake.last_prompt is not None

def test_none_fields_dont_leak_into_prompt():
    """When narration_line is None, the guards must render an empty
    slot, not the literal string 'None'."""
    fake = FakeLLM(_canned_verdict())
    judge = GroundednessJudge(llm=fake)

    judge.judge(_sample_gap(), _none_fields_pitch())

    assert "None" not in fake.last_prompt 