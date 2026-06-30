"""
LLM-as-judge for generated TikTok scripts — P3 eval gate.

PIPELINE ROLE:
  Generated script → LLM judge (this file) → verdict (score, hook_strength, reasoning, preferred)

WHY THIS FILE EXISTS:
  P3 generation requires eval feedback to close the loop. Rather than free-text
  responses (non-reproducible), we use Anthropic structured-output to return typed
  JudgeVerdict objects. This allows aggregation across eval runs and integration
  with harness.py for CI gates (e.g., avg_score ≥ 3.5 to ship).

DUAL MODE:
  1. judge(script): single-script scoring (1-5 scale, hook strength, reasoning)
  2. judge_pairwise(rag_script, baseline_script): A/B preference (preferred: rag/baseline/tie)

REPRODUCIBILITY:
  Structured-output ensures every verdict is parseable and typed (not a blob
  of text). This enables meta-eval: score the judge by comparing its preferences
  against golden labels from human reviewers (future P5 work).
"""

from pydantic import BaseModel, Field
from typing import Literal
from src.providers.llm.anthropic_llm import AnthropicLLM


SYSTEM_PROMPT = """You are an expert TikTok content strategist evaluating AI-generated video scripts.
Score the script on a 1-5 scale based on: hook strength, clarity, engagement potential, and fit for the video's niche.
Be concise and critical. Low scores are valid."""

class JudgeVerdict(BaseModel): 
    """
    Structured verdict from LLM judge on a script.
    
    Attributes:
      score: 1-5 quality rating
      hook_strength: qualitative assessment (weak/moderate/strong)
      reasoning: brief justification (max 300 chars, for audit trail)
      preferred: set to 'rag', 'baseline', or 'tie' ONLY during pairwise comparison.
                 None during single-script scoring.
    """
    score: int = Field(ge=1, le=5, description="Overall quality score 1-5")
    hook_strength: Literal["weak", "moderate", "strong"]
    reasoning: str = Field(max_length=600, description="Brief justification for the score")
    preferred: Literal["baseline", "rag", "tie"] | None = Field(
        default=None,
        description="Set only for pairwise comparison; None for single-script scoring"
    )

class ScriptQualityJudge:
    """
    LLM-as-judge scoring TikTok scripts on a 1-5 quality scale.
    """

    def __init__(self, model: str = "claude-sonnet-5"):
        self.llm = AnthropicLLM(model=model)

    def judge(self, video_stats: dict, script: str) -> JudgeVerdict:
        """
        Score a single script (not pairwise). Returns verdict with preferred=None.
        
        Args:
            video_stats: dict with keys views, likes, comments, shares, virality_class
            script: generated script text to evaluate
        
        Returns:
            JudgeVerdict with score (1-5), hook_strength, reasoning, preferred=None
        """
        prompt = (
            f"Video stats:\n"
            f" Views: {video_stats.get('views', 0):,}\n"
            f" Likes: {video_stats.get('likes', 0):,}\n"
            f" Comments: {video_stats.get('comments', 0):,}\n"
            f" Shares: {video_stats.get('shares', 0):,}\n"
            f" Virality class: {video_stats.get('virality_class', 'unknown')}\n\n"
            f"Generated script:\n{script}\n\n"
            f"Score this script."
        )
        return self.llm.parse(
            prompt,
            response_model=JudgeVerdict,
            system=SYSTEM_PROMPT,
        )

    def judge_pairwise(self, video_stats: dict, rag_script: str, baseline_script: str) -> JudgeVerdict:
        """
        Compare two scripts side-by-side. Returns verdict with preferred set.
        
        Args:
            video_stats: dict with video metadata
            rag_script: script generated with RAG context
            baseline_script: script generated without RAG
        
        Returns:
            JudgeVerdict with score (1-5), hook_strength, reasoning, and preferred:
              'rag': RAG script is better
              'baseline': baseline script is better
              'tie': both equally good/bad
        """
        prompt = (
                f"Video stats:\n"
                f"  Views: {video_stats.get('views', 0):,}\n"
                f"  Virality class: {video_stats.get('virality_class', 'unknown')}\n\n"
                f"Script A (RAG):\n{rag_script}\n\n"
                f"Script B (Baseline):\n{baseline_script}\n\n"
                f"Which script is better? Set preferred to 'rag', 'baseline', or 'tie'."
            )
        return self.llm.parse(
            prompt=prompt,
            response_model=JudgeVerdict,
            system=SYSTEM_PROMPT,
        )