"""
LLM-as-judge for generated TikTok scripts.

Single-script scoring and pairwise (RAG vs baseline) preference, both
returned as typed Pydantic verdicts via Anthropic structured-output —
free-text judges can't be aggregated reproducibly across eval runs.
"""

from pydantic import BaseModel, Field
from typing import Literal
from src.providers.llm.anthropic_llm import AnthropicLLM


SYSTEM_PROMPT = """You are an expert TikTok content strategist evaluating AI-generated video scripts.
Score the script on a 1-5 scale based on: hook strength, clarity, engagement potential, and fit for the video's niche.
Be concise and critical. Low scores are valid."""

class JudgeVerdict(BaseModel): 
    score: int = Field(ge=1, le=5, description="Overall quality score 1-5")
    hook_strength: Literal["weak", "moderate", "strong"]
    reasoning: str = Field(max_length=300, description="Brief justification for the score")
    preferred: Literal["baseline", "rag", "tie"] | None = Field(
        default=None,
        description="Set only for pairwise comparison; None for single-script scoring"
    )

class ScriptQualityJudge:
    """
    LLM-as-judge scoring TikTok scripts on a 1-5 quality scale.
    """

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.llm = AnthropicLLM(model=model)

    def judge(self, video_stats: dict, script: str) -> JudgeVerdict:
        """
        Score a single script against the video it was generated for.
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
        Compare two scripts. Returns verdict with preferred set.
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