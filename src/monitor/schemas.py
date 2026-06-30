from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GapType(str, Enum):
    alternate_reality = "alternate_reality"  # show the version that should've happened (denied ending, what-if)
    vindication = "vindication"  # prove the side they back was right
    ridicule = "ridicule"  # mock the thing/person everyone's piling on
    explanation = "explanation"  # make a confusing event make sense
    tribute = "tribute"  # honor / celebrate something they love
    speculation = "speculation"  # show what happens next
    solidarity = "solidarity"  # voice the feeling everyone's sharing
    other = "other"


class RenderBackend(str, Enum):
    visual_satire = "visual_satire"
    commentary_voiceover = "commentary_voiceover"
    narrative_alt = "narrative_alt"
    unknown = "unknown"


class TrendingEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    subreddit: str
    url: str
    reaction_sample: str
    trendiness_score: float
    virality_window_hours: float
    raw_source_data: dict
    origin: Literal["scraped", "manual"]


class GapAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dominant_emotion: str
    audience_want: str
    gap_type: GapType
    producibility_score: float
    virality_window_hours: float
    reasoning: str


class AnglePitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    take: str
    format_description: str
    render_backend: RenderBackend
    estimated_cost_credits: float
    gap_satisfaction_rationale: str
    legal_flag: bool


class AnglePitchSlate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    angles: list[AnglePitch] = Field(min_length=3, max_length=3)


class RoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: RenderBackend
    is_substitute: bool
    substitution_note: str | None


class DedupVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_same: bool


class ContentMode(str, Enum):
    wish = "wish"  # fans want the satisfying version they didn't get
    satire = "satire"  # fans want their disappointment voiced as humor/contrast
    other = "other"


class IdeaFitResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idea_fit: bool
    mode: ContentMode
    heat_score: float = Field(ge=0.0, le=1.0)  # LLM-judged reaction passion
    recency_days: float  # post age in days, derived from raw_source_data
    reason: str  # human-readable verdict
    kill_reason: str | None  # set when idea_fit=False; None when the event passes


class PlanDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_action: Literal["reddit_search", "tavily_search", "stop"]
    next_query: str  # search query to use; empty when next_action == "stop"


class ContextSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    key_moments: list[str]


class ContextBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reaction_sample: str
    summary: str
    key_moments: list[str]
    references: list[str]
    sources: list[str]
