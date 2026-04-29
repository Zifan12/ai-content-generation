from pydantic import BaseModel, Field
from typing import Literal

class VideoHookVariant(BaseModel):
    hook_text: str # the opening line/hook
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
    virality_score: float # 0.0–1.0
    confidence: float     # how sure the model is
    trend_stage: Literal["emerging", "peak", "declining", "dead"] # emerging = act fast, peak = compete now, declining = skip
    reasoning: str # why it's viral
    signals:list[str] # specific evidence: ["hashtag +340% in 24h", "3 top creators posted same format"]
    recommended_hooks: list[str]  # which hook_types fit this trend best

class SafetyCheck(BaseModel):
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
    
