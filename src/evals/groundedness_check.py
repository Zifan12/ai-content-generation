"""
LLM-as-judge measuring EVIDENCE GROUNDEDNESS of a StoryPitch — the ablation
scorer for the pitcher-genericness fix.

PIPELINE ROLE:
  (GapAnalysis, StoryPitch) -> GroundednessJudge -> GroundednessVerdict
  (one row per evidence item + swap-test result)

WHY THIS FILE EXISTS:
  The StoryPitcher is suspected of ignoring the real gathered evidence and
  defaulting to the mode-playbook's worked example, producing pitches that are
  generically on-topic but not grounded in THIS event's specifics. This judge
  scores that groundedness so a controlled ablation (playbook example present
  vs. stripped) can be diffed. Per Daniel Commey's eval framework this is a
  correct-but-unsupported / groundedness measurement: score per-evidence-item,
  never one holistic scalar.

GUARDRAILS (see docs/superpowers/plans/2026-07-03-pitcher-groundedness-fix.md):
  - Cross-family judge (Sonnet-5 judging the DeepSeek pitcher) — self-preference.
  - Reference-based: the judge sees the verbatim GapAnalysis evidence.
  - The judge is NEVER shown the mode playbook's worked example or which ablation
    arm produced the pitch (criteria-leakage guard).
  - Chain-of-thought (`reasoning`) is emitted before any label (verbosity guard).
"""

from pydantic import BaseModel, Field
from typing import Literal
from src.providers.llm.anthropic_llm import AnthropicLLM
from src.providers.llm.openrouter_llm import OpenRouterLLM
from src.monitor.schemas import GapAnalysis, StoryPitch


SYSTEM_PROMPT = """You are a strict evaluator measuring the EVIDENCE GROUNDEDNESS of a story pitch.

You are given (a) a GapAnalysis holding the REAL, specific evidence gathered about ONE audience reaction — its dominant emotion, what the audience wants, and up to three verbatim reaction quotes — and (b) a StoryPitch generated from it.

Your only question: does the pitch actually USE this event's specific evidence, or is it merely generically on-topic about the same characters? A pitch that would fit almost any character in the franchise is NOT grounded, even when it is well written.

For EACH evidence item you are given (dominant_emotion, audience_want, and each quote), output one row in evidence_items:
- label = "grounded"    -> the pitch clearly and specifically reflects that item (names the exact detail, moment, or desire).
- label = "paraphrased" -> the pitch reflects the item's substance in different words, still clearly traceable to it.
- label = "absent"      -> the pitch does not use that item at all.
- evidence_quote = the evidence item's text (the quote, or the emotion/want string).
- pitch_span = the shortest snippet of the PITCH that shows the grounding, or "" when absent.

Then run the SWAP TEST: could this exact pitch text stay equally plausible if a DIFFERENT character's evidence were substituted, holding the pitch text fixed? If yes, set swap=true — that is a bad sign, it means the pitch is generic. Give a one-sentence swap_justification.

RULES:
- Fill `reasoning` with your step-by-step analysis BEFORE assigning any labels.
- Be strict. Surface topical overlap (same character, same general vibe) is NOT grounding.
- Judge only what the pitch text shows. Do not reward length or fluent writing.
- Do not assume any template, example, or "correct" pitch shape — judge the pitch on its own text against the evidence alone.
"""

# The verdict is a full per-evidence-item rubric plus an uncapped CoT reasoning
# field, which overflows parse()'s shared 1024 default and truncates mid-JSON —
# the same trap as _PITCH_MAX_TOKENS (story_pitcher.py) and WRITER_MAX_TOKENS.
# Per-caller override, never raise the shared default. Observed verdicts run
# ~600-1000+ output tokens; 4096 leaves headroom for a long reasoning walk.
_GROUNDEDNESS_MAX_TOKENS = 4096

class EvidenceItemVerdict(BaseModel):
    evidence_quote: str
    label: Literal["grounded", "paraphrased", "absent"]
    pitch_span: str


class GroundednessVerdict(BaseModel):
    reasoning: str = Field(description="")
    swap: bool
    swap_justification: str = Field()
    evidence_items: list[EvidenceItemVerdict]


class GroundednessJudge:
    """
    LLM-as-judge scoring whether a StoryPitch is grounded in its source
    GapAnalysis evidence (vs. merely generically on-topic about the same IP).

    Reference-based: the judge is shown the verbatim GapAnalysis evidence and the
    pitch text only. It is never shown the mode playbook's worked example or which
    ablation arm produced the pitch (criteria-leakage guard).
    """

    def __init__(self, llm: AnthropicLLM | OpenRouterLLM):
        self.llm = llm

    def judge(self, gap: GapAnalysis, pitch: StoryPitch) -> GroundednessVerdict:
        """
        Score one pitch's groundedness against its source GapAnalysis.

        Args:
            gap: the GapAnalysis whose evidence the pitch was generated from.
            pitch: the StoryPitch to evaluate.

        Returns:
            GroundednessVerdict with one EvidenceItemVerdict row per evidence
            item (dominant_emotion, audience_want, each quote), the swap-test
            bool + justification, and the judge's chain-of-thought reasoning.
        """
        evidence_lines = "\n".join(
            f"  quote {i}: {quote}"
            for i, quote in enumerate(gap.evidence_quotes, start=1)
        )
        beat_lines = "\n".join(
            f"  [{beat.role.value}] {beat.visual_line}"
            + (f" | narration: {beat.narration_line}" if beat.narration_line else "")
            for beat in pitch.beats
        )
        prompt = (
            f"EVIDENCE (from the GapAnalysis — the real reaction):\n"
            f"  dominant_emotion: {gap.dominant_emotion}\n"
            f"  audience_want: {gap.audience_want}\n"
            f"{evidence_lines}\n\n"
            f"Evidence items to score (one row each): dominant_emotion, "
            f"audience_want, and each quote above.\n\n"
            f"PITCH TO EVALUATE:\n"
            f"  logline: {pitch.logline}\n"
            f"  desired_moment: {pitch.desired_moment}\n"
            f"  why_it_lands: {pitch.why_it_lands}\n"
            f"  hook_line: {pitch.hook_line or ''}\n"
            f"  beats:\n{beat_lines}\n\n"
            f"Score this pitch's groundedness in the evidence."
        )
        return self.llm.parse(
            prompt,
            response_model=GroundednessVerdict,
            system=SYSTEM_PROMPT,
            max_tokens=_GROUNDEDNESS_MAX_TOKENS,
        )


