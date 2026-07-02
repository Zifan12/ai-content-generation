from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


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


class BeatRole(str, Enum):
    """Ordered story-beat roles a StoryPitch arc is built from (spec 06-27)."""

    hook = "hook"  # opening beat that stops the scroll
    establish = "establish"  # set the world / normal state
    build = "build"  # raise tension toward the turn
    turn = "turn"  # the pivot — the denied thing starts to happen
    escalate = "escalate"  # push the premise further (satire's engine)
    reveal = "reveal"  # show the payoff moment
    payoff = "payoff"  # deliver the earned satisfaction
    tag = "tag"  # the button / closing beat


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
    apify_cost_estimate: float = 0.0

    def to_context_block(self) -> str:
        """Render this bundle as a ``<context>`` block for prompt injection.

        Used by GapAgent and AnglePitcher to ground their prompts in the
        web-research the context agent gathered.  Keeps the same untrusted-data
        delimiting discipline (tagged block) those prompts already use.

        Returns an empty string when the bundle carries no real content; callers
        should check the return value and skip injection when empty.
        """
        if not self.summary and not self.key_moments and not self.references:
            return ""
        lines = ["<context>", f"summary: {self.summary}"]
        if self.key_moments:
            bullets = "\n".join(f"- {m}" for m in self.key_moments)
            lines.append("key_moments:")
            lines.append(bullets)
        if self.references:
            lines.append("references:")
            lines.append("\n".join(f"- {r}" for r in self.references))
        lines.append("</context>")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Story-craft models (Stage B, spec 06-27). ADDITIVE: the legacy GapType /
# RenderBackend / AnglePitch / AnglePitchSlate / RoutingDecision classes and the
# old GapAnalysis above are deleted/rewritten in their consumer tasks (3 = gap
# agent, 4 = pitcher/router), not here, so the test suite stays green.
# ---------------------------------------------------------------------------


class ShotSize(str, Enum):
    """Camera distance for a single beat (widest -> tightest)."""

    establishing = "establishing"
    wide = "wide"
    medium = "medium"
    close_up = "close_up"
    extreme_close_up = "extreme_close_up"
    over_shoulder = "over_shoulder"


class CaptionPolicy(str, Enum):
    """How captions are used on the rendered video."""

    none = "none"  # no on-screen text
    hook_only = "hook_only"  # a single hook card, no explainer captions


class CharacterRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    ip_source: str  # the work the character is from (e.g. "Stellar Blade")
    needs_reference: bool = True  # whether render must ground on real key-art


class StoryBeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: BeatRole
    visual_line: str  # what the camera sees this beat (render-facing)
    narration_line: str | None  # optional VO/caption line; None = silent beat
    shot_size: ShotSize
    characters_in_frame: list[str]  # CharacterRef names present in this beat
    hero_moment: bool = False  # the one payoff beat; at most one per pitch


class StoryPitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logline: str
    mode: ContentMode
    characters: list[CharacterRef]
    desired_moment: str  # the thing the reaction is begging to see
    beats: list[StoryBeat] = Field(min_length=3, max_length=6)
    caption_policy: CaptionPolicy = CaptionPolicy.hook_only
    hook_line: str | None = None  # required iff caption_policy == hook_only
    why_it_lands: str
    legal_flag: bool  # True = likeness/IP concern to review before render

    @model_validator(mode="after")
    def _check_beat_and_caption_rules(self) -> "StoryPitch":
        """
        Enforce cross-field craft rules a single-field validator cannot see.

        - Beats must not ALL share one shot_size (forces framing variety — the
          BUG-002 static-shotcraft failure mode).
        - At most one beat may be the hero_moment.
        - hook_line must be present exactly when caption_policy is hook_only.
        """
        if len({beat.shot_size for beat in self.beats}) == 1:
            raise ValueError(
                "all beats share one shot_size; vary framing (establish/detail/reveal)"
            )
        hero_count = sum(beat.hero_moment for beat in self.beats)
        if hero_count > 1:
            raise ValueError(
                f"at most one hero_moment beat allowed, found {hero_count}"
            )
        has_hook = bool(self.hook_line)
        wants_hook = self.caption_policy == CaptionPolicy.hook_only
        if wants_hook and not has_hook:
            raise ValueError("caption_policy=hook_only requires a hook_line")
        if has_hook and not wants_hook:
            raise ValueError("hook_line set but caption_policy is not hook_only")
        return self


class StoryPitchSlate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pitches: list[StoryPitch] = Field(min_length=2, max_length=3)


class StoryCraftVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clear_desire: bool  # is the audience want unmistakable?
    visible_turn: bool  # is there an on-screen pivot?
    earned_payoff: bool  # does the payoff follow from the turn?
    emotion_physical_tell: bool  # emotion shown as action, not labeled?
    notes: str
    failure_notes: str | None  # what to fix on a repair re-pitch; None if it passes
    would_watch: bool

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passes(self) -> bool:
        """Pass only if all four craft dims hold AND the pitch is watchable."""
        return (
            self.clear_desire
            and self.visible_turn
            and self.earned_payoff
            and self.emotion_physical_tell
            and self.would_watch
        )


