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
    """One beat of a pitch: the idea for a single shot.

    The beat is the IDEA, not the finished prompt — the director stage downstream
    elevates it with craft (camera, sound, physical detail) and is expected to. But
    it may not lose the beat's SPINE: ``destination`` and ``required_action`` name
    the facts the story collapses without, and code (not a prompt) asserts they
    survive into the shipped scene line.

    Why the spine is structured and not just prose: on 2026-07-15 the writer turned
    the pitch's "pulling him toward the bed" into "dragged backward across the room"
    and dropped "lifts Will onto the bed" entirely. Both losses shipped, and the
    rendered video cut from the drag straight to the end-state — the lift never
    happened on screen because nothing asked for it. Prose cannot be checked
    deterministically ("the bed" is not extractable from a sentence without NLP), so
    the beat states its own non-negotiables as fields the adapter can assert on.
    See .scratch/director-stage/PRD.md.
    """

    model_config = ConfigDict(extra="forbid")

    role: BeatRole
    visual_line: str  # what the camera sees this beat (render-facing)
    destination: str | None = None
    """WHERE the beat's motion POINTS — aimed at, not necessarily reached.

    A short noun phrase naming the place or object the motion is aimed at. Note
    "points", not "arrives": a character crawling toward an exit they never reach
    still has that exit as their destination, and it is exactly as load-bearing —
    drop it and the beat is a person moving for no reason. An earlier draft of
    this field tied it to arrival and the pitcher correctly left it null on every
    beat whose goal was denied, which is most of the interesting ones.

    ``None`` is legitimate: a beat whose motion points nowhere ("she smirks at
    the camera") has no destination, and the downstream check skips (loudly)
    rather than inventing one.

    Optional ONLY for backwards compatibility: ``story_json`` rows written before
    2026-07-15 have no such field and must still load (pitch 47 is the only real
    evidence we have about this bug). New pitches set it whenever the story has a
    destination at all.
    """
    required_action: str | None = None
    """The ONE flowing motion this beat exists to show. MOTION ONLY — never a face.

    One continuous move, however many sub-motions it takes — "lifts Will onto the
    bed and cradles him" is ONE action, not two. The sub-motions of a single
    flowing gesture belong together; splitting them reads as two shots (Dan Kieft
    L471: "One flowing motion per shot... not a setup sentence + an 'after he
    finishes…' block"). Do NOT reduce it to one verb: reducing "lifts... and
    cradles" to "cradles" is exactly the loss that produced the pitch-47 failure.

    **No expression, mood, or facial state belongs in this field** (added
    2026-07-15, ticket 04). Pitch 50 shipped ``"lifting Will's limp body onto the
    bed and cradling him against her chest, holding his lolling head, looking down
    with a satisfied smirk"`` — the trailing clause is expression, not motion, and
    it leaked in from the beat's prose. It matters because CODE holds this field as
    the story's spine: an expression parked here would be enforced as though it
    were the movement, which is the one thing D7 forbids (a static adjective on a
    face renders as a generic pleasant expression and inverts the intended
    register — measured on pitch 47's payoff). Emotion is the render stage's craft,
    written as a CHANGE at close-ups; it lives in ``visual_line``, never here.

    Optional ONLY for backwards compatibility — see ``destination``.
    """
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
    scene_setting_contained: bool  # every beat stays inside ONE Scene Space (+ <=1 threshold)
    one_action_per_beat: bool  # each beat stages ONE flowing motion, however many sub-motions
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
            and self.one_action_per_beat
            and self.would_watch
        )


