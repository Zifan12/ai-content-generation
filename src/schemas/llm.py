"""
Pydantic schemas for LLM I/O and Blueprint extraction.

PIPELINE ROLE:
  Blueprint extractor → VideoHookVariant/TrendAnalysis/SafetyCheck (this file) → serialize to DB → RAG/generation

WHY THIS FILE EXISTS:
  Structured schemas ensure LLM outputs are type-safe and reproducible. Used with
  Anthropic structured-output (instructor) for deterministic JSON responses.

KEY SCHEMAS:
  - VideoHookVariant: hook types and CTR estimates (P3 generation)
  - TrendAnalysis: virality signals, trend stage, recommended hooks (P1 trend detection)
  - SafetyCheck: content moderation verdicts and flags (P3 safety gate)
"""

from pydantic import BaseModel, Field
from typing import Literal

class VideoHookVariant(BaseModel):
    """
    Hook copy variant with type and predicted click-through rate.
    
    Attributes:
      hook_text: actual hook copy (1-2 sentences)
      hook_type: categorical type (hot_take, curiosity_gap, etc.)
                 Used as feature in Blueprint extraction and generation variants
      estimated_ctr: LLM's estimate of click-through rate (0.0-1.0, for ranking)
    """
    hook_text: str
    hook_type: Literal[
        "hot_take",
        "flip_the_script",
        "talk_to_camera",
        "curiosity_gap",
        "show_something_wild",
        "predict_the_future",
        "lead_with_proof",
        "story",
        "pain_point",
        "warning",
        "how_to",
        "listicle",
        "transformation",
        "cliffhanger",
        "direct_address",
        "trend_jack",
        "challenge",
        "pov",
    ]
    estimated_ctr: float # 0.0-1.0

class TrendAnalysis(BaseModel):
    """
    Trend virality analysis with stage and recommended hooks.
    
    Output of trend detection + LLM analysis (P1). Used to rank scraped content
    for approval in the approval workflow.
    
    Attributes:
      virality_score: 0.0–1.0 likelihood this trend will go viral
      confidence: model confidence in the score (0.0-1.0)
      trend_stage: lifecycle stage dictating strategy
        - "emerging": first movers win (act fast)
        - "peak": highest competition (quality matters most)
        - "declining": declining odds (skip unless unique angle)
        - "dead": too late (don't bother)
      reasoning: plain-text explanation (audit trail)
      signals: list of specific evidence ("hashtag +340% in 24h", "3 creators posted")
               Makes the analysis auditable and reproducible
      recommended_hooks: list[str] of hook types that work well for this trend
                        Used by generation (P3) to condition prompt
    """
    virality_score: float # 0.0–1.0
    confidence: float
    trend_stage: Literal["emerging", "peak", "declining", "dead"] # emerging = act fast, peak = compete now, declining = skip
    reasoning: str
    signals:list[str] # specific evidence: ["hashtag +340% in 24h", "3 top creators posted same format"]
    recommended_hooks: list[str]

class SafetyCheck(BaseModel):
    """
    Content moderation verdict and flagged risks.
    
    Used in P3 generation safety gate to reject unsafe content before posting.
    
    Attributes:
      is_safe: boolean pass/fail
      severity: categorical risk level
        - "ok": safe to generate/post
        - "warning": caution advised (manual review recommended)
        - "block": reject (do not generate or post)
      reason: explanation (e.g., "Contains hate speech directed at religion X")
      flags: list of detected issues (hate_speech, misinformation, etc.)
             Each flag is evidence for the verdict (e.g., 2+ flags = block)
    """
    is_safe: bool
    severity: Literal["ok", "warning", "block"]
    reason: str | None = None
    flags: list[Literal[
          "hate_speech",
          "misinformation",
          "explicit_content",
          "copyright",
          "spam",
          "violence",
          "platform_tos",
    ]]
    
