from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


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
    evidence_quotes: list[str] = Field(default_factory=list, max_length=3)
    reasoning: str


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

    next_action: Literal["reddit_search", "tavily_search", "firecrawl_extract", "stop"]
    next_query: str  # search query to use; empty unless next_action is reddit_search/tavily_search
    next_url: str = ""  # URL to fetch in full; set only when next_action == "firecrawl_extract"


class ContextSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    key_moments: list[str]
    unresolved_facts: list[str] = Field(default_factory=list)


class ContextBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reaction_sample: str
    summary: str
    key_moments: list[str]
    references: list[str]
    sources: list[str]
    apify_cost_estimate: float = 0.0
    unresolved_facts: list[str] = Field(default_factory=list)

    def to_context_block(self) -> str:
        """Render this bundle as a ``<context>`` block for prompt injection.

        Used by GapAgent and StoryPitcher to ground their prompts in the
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
        if self.unresolved_facts:
            lines.append("unresolved_facts:")
            lines.append("\n".join(f"- {f}" for f in self.unresolved_facts))
        lines.append("</context>")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Story-craft models (Stage B, spec 06-27). These are THE monitor content models:
# a pitch is a shootable story (protagonist + ordered beats), judged on craft.
# The routing-era classes (GapType / RenderBackend / AnglePitch / AnglePitchSlate /
# RoutingDecision) were removed in the Task 7 orchestration swap.
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
    dialogue_line: str | None = None  # optional spoken line, quoted-speech form
    speaker: str | None = None  # must be one of characters_in_frame; set iff dialogue_line is
    shot_size: ShotSize
    characters_in_frame: list[str]  # CharacterRef names present in this beat
    hero_moment: bool = False  # the one payoff beat; at most one per pitch

    @model_validator(mode="after")
    def _check_dialogue_speaker_rule(self) -> "StoryBeat":
        """
        dialogue_line and speaker are a pair: both set or both None. When set,
        speaker must be a name already present in this beat's characters_in_frame
        — a line spoken by someone not on screen is a lip-sync bug waiting to
        happen (spec §5 KNOWN UNKNOWNS: "wrong character speaks" has no
        documented mitigation beyond this).
        """
        has_dialogue = self.dialogue_line is not None
        has_speaker = self.speaker is not None
        if has_dialogue != has_speaker:
            raise ValueError(
                "dialogue_line and speaker must both be set or both be None"
            )
        if has_speaker and self.speaker not in self.characters_in_frame:
            raise ValueError(
                f"speaker {self.speaker!r} must be one of "
                f"characters_in_frame {self.characters_in_frame}"
            )
        return self


class StoryPitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logline: str
    mode: ContentMode
    characters: list[CharacterRef]
    desired_moment: str  # the thing the reaction is begging to see
    scene_setting: str = ""  # the ONE place/time every beat stays inside; "" = pre-v2 row
    beats: list[StoryBeat] = Field(min_length=3, max_length=5)
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
    cold_viewer_legible: bool  # premise readable from visuals alone, zero context
    kinetic_payoff: bool  # the peak beat is physical and camera-visible, not a held pose
    register_match: bool  # comedic/earnest/satirical register matches gap.audience_want
    dialogue_earns_place: bool  # any dialogue_line pulls its weight; true if there is none
    scene_setting_contained: bool  # every beat stays inside the declared scene_setting
    notes: str
    failure_notes: str | None  # what to fix on a repair re-pitch; None if it passes
    would_watch: bool

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passes(self) -> bool:
        """Pass only if every craft dimension holds AND the pitch is watchable."""
        return (
            self.clear_desire
            and self.visible_turn
            and self.earned_payoff
            and self.emotion_physical_tell
            and self.cold_viewer_legible
            and self.kinetic_payoff
            and self.register_match
            and self.dialogue_earns_place
            and self.scene_setting_contained
            and self.would_watch
        )


