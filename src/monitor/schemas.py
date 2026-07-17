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
# Exilus lane models (PRD 2026-07-17): topic-to-slate front-end. TopicBrief is
# the pinned research artifact — five fixed fields, each independently citable
# and independently markable UNVERIFIED (checker-exhaustion path, ticket 03/04).
# TopicBriefDraft is the LLM's raw output (content+citations only, no verified
# flags — the LLM that authored a field is never the one that grades it); code
# composes TopicBrief from the draft plus the checker's per-field verdicts, the
# same ScriptDraft -> StoryScript composition-in-code precedent used above.
# ---------------------------------------------------------------------------


class BriefFieldDraft(BaseModel):
    """One TopicBrief field as the LLM writes it: content + its citations.

    No ``verified`` flag here — the researching LLM never grades its own
    work. A separate cross-family checker (ticket 03/04) decides pass/fail
    per field; code then composes the matching :class:`BriefField` with
    ``verified`` set from that verdict.
    """

    model_config = ConfigDict(extra="forbid")

    content: str
    citations: list[str] = Field(default_factory=list)  # source URLs


class TopicBriefDraft(BaseModel):
    """The LLM's raw synthesis of the five TopicBrief fields (pre-checker)."""

    model_config = ConfigDict(extra="forbid")

    identity: BriefFieldDraft
    recent_events: BriefFieldDraft
    key_characters: BriefFieldDraft
    why_people_care: BriefFieldDraft
    open_unknowns: list[str] = Field(default_factory=list)


class BriefField(BaseModel):
    """One TopicBrief field: its written content, the source citation(s) it
    draws on, and whether it has passed the checker.

    ``citations`` and ``content`` are kept as separate, independently
    inspectable fields (never concatenated into one string) so a downstream
    checker can verify "every citation URL is in the gathered URL set"
    without parsing prose. ``verified`` defaults ``True`` because most
    fields are composed straight from a passing checker verdict; the
    checker-exhaustion repair path (ticket 03/04) is the one place that
    constructs a field with ``verified=False`` — the brief's UNVERIFIED
    stamp, held per-field rather than as one brief-wide flag, since one
    field failing must not discard the other four fields' good citations.
    """

    model_config = ConfigDict(extra="forbid")

    content: str
    citations: list[str] = Field(default_factory=list)  # source URLs
    verified: bool = True


class TopicBrief(BaseModel):
    """The pinned research artifact for one Exilus topic (PRD's five fixed
    questions): what is this; what recently happened; key characters and
    relationships; why people care; open unknowns.

    Persisted once per topic in ``ExilusTopicRecord.brief_json`` and REPLACED
    (never merged) on an explicit refresh. ``open_unknowns`` is
    citation-free by design — it mirrors the existing
    ``unresolved_facts``/``ContextSynthesis.unresolved_facts`` concept: a
    list of gaps the research loop could not close, not claims that need a
    source.

    No ``wave_status`` field (user decision — freshness is out of scope for
    this artifact) and no visual/lore-dump fields (those belong to the
    downstream director, not the brief).
    """

    model_config = ConfigDict(extra="forbid")

    identity: BriefField
    recent_events: BriefField
    key_characters: BriefField
    why_people_care: BriefField
    open_unknowns: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Faction Map models (PRD ticket 05): the audience-camp artifact that replaces
# the single-consensus GapAnalysis for the Exilus lane. Camp emergence is
# UNCONSTRAINED during generation (FactionMapDraft, the LLM's raw output);
# code caps the emerged camps to 5 (highest weight first) when composing the
# pinned FactionMap -- the same "unconstrained draft, code-composed final
# artifact" precedent as ScriptDraft -> StoryScript above.
# ---------------------------------------------------------------------------


class EvidenceQuote(BaseModel):
    """One verbatim audience quote backing a camp, paired with its source upvote count.

    ``upvotes`` defaults to 0 rather than being optional -- mirrors
    ``reddit_search``'s own missing-score fallback (a comment whose tag
    degraded to a bare ``[COMMENT]``, no readable score, still needs a
    sortable/reportable number, and "unknown reads as 0" is the convention
    ``reddit_search.py``'s own ``_upvotes`` helper already uses).
    """

    model_config = ConfigDict(extra="forbid")

    quote: str
    upvotes: int = 0


class Camp(BaseModel):
    """One audience camp within a FactionMap.

    ``surface_want`` is what the audience said, in their own words.
    ``deeper_desire`` is Exilus's own INFERRED guess at what's underneath
    that -- always a best-effort inference from unprompted forum text (no
    follow-up questions were possible), never to be read as a confirmed fact
    just because it sits next to ``surface_want`` in the same record (Indi
    Young's surface-vs-interior-want distinction; PRD Further Notes' "depth
    ceiling accepted" doctrine). ``weight`` is this camp's share of the
    surviving (>=5-upvote) comments the map was built from -- a triage
    signal, not a scientific poll; the PRD leaves whether weights across a
    map must sum to 1.0 unspecified, so this is an independently-computed
    per-camp share, not a validated total.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    feeling: str
    surface_want: str
    deeper_desire: str  # INFERRED -- see class docstring; never conflate with surface_want
    evidence_quotes: list[EvidenceQuote] = Field(default_factory=list)
    weight: float


class FactionMapDraft(BaseModel):
    """The LLM's raw camp emergence: UNCONSTRAINED camp count.

    Camp emergence must not be forced into a preset count (PRD User Story
    12) -- the 5-camp cap is a POST-generation filter code applies when
    composing the pinned ``FactionMap``, never a schema constraint on this
    draft.
    """

    model_config = ConfigDict(extra="forbid")

    camps: list[Camp]


class FactionMap(BaseModel):
    """The pinned Exilus audience-camp artifact (PRD ticket 05), replacing
    the single-consensus ``GapAnalysis`` for this lane.

    ``camps`` is capped to 5 (composed in code from a ``FactionMapDraft``,
    kept by weight descending) -- a single surviving camp is legal, not an
    error or a padding target (PRD User Story 13). ``thin_data`` is stamped
    True when the map was built on fewer than the ~30-surviving-comment
    floor even after the one permitted top-up call; False otherwise.

    ``min_length=1``: an EMPTY map must never validate here -- it would let
    ideation's per-camp coverage check pass vacuously (zero camps to cover is
    trivially "every camp covered"), silently shipping a slate with no real
    audience grounding. ``FactionMapDraft`` (the LLM's raw, pre-cap output)
    is deliberately left unconstrained -- a draft emerging zero camps is the
    reader's OWN signal to retry, not a shape this schema should forbid at
    the LLM boundary; see ``FactionReader.read``'s bounded retry.
    """

    model_config = ConfigDict(extra="forbid")

    camps: list[Camp] = Field(min_length=1, max_length=5)
    thin_data: bool = False


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

    @model_validator(mode="after")
    def _check_spine_pair_rule(self) -> "StoryBeat":
        """
        A destination requires a motion to reach for it — but not the reverse.

        The implication runs ONE WAY: ``destination`` set means ``required_action``
        must be set too. A target with no motion aimed at it is incoherent — the
        beat names somewhere to go and shows nobody going.

        The reverse is legal and load-bearing: an action with NO destination is a
        motion that genuinely goes nowhere ("she smirks straight down the lens"),
        which ``destination``'s own docstring names as a deliberate null. Both null
        is also legal — pre-2026-07-15 ``story_json`` rows have neither field and
        must still load.

        NOT symmetric, unlike the sibling dialogue/speaker rule above. That one is
        a true pair (a line needs a mouth, a mouth needs a line). This one is an
        implication, and an early draft of this validator got it wrong by copying
        the dialogue rule's shape — caught by
        ``test_beat_with_no_destination_is_legitimate``, which pins exactly the
        case the symmetric version banned.

        Deliberately NARROW, and the limit is worth stating: this catches SILENT
        OMISSION only. It does NOT catch the pitch-51 failure (2026-07-16), where
        both fields were filled and disagreed in KIND — destination "the doorway's
        threshold" against required_action "clawing weakly at the floor", a
        stationary gesture that never travels. Whether prose actually closes on a
        noun phrase is a semantic question, and the rejected spine check
        (2026-07-15: "a synonym and a dropped fact are both just different words")
        is the evidence that code cannot answer it. That rule lives in the
        pitcher's field spec — a prompt rule, weak by construction, and knowingly
        so.
        """
        if self.destination is not None and self.required_action is None:
            raise ValueError(
                f"destination {self.destination!r} is set but required_action is "
                "None — a destination is where a motion is AIMED; name the motion "
                "or drop the destination"
            )
        return self


class IdeaPitch(BaseModel):
    """The pitcher's whole output for one pitch: the DESIRE, nothing staged.

    Slice ① of the staged-director design (spec 2026-07-16): the pitcher names
    the moment a reaction wave is begging to see and WHO is in it — it authors
    no beats, no shot sizes, no dialogue, no scene staging. Story structure is
    the StoryArchitect's job (src/generation/story_architect.py), which holds
    the craft knowledge the pitcher never had (obs 2206: pitch-51's beat-free
    action line was authored here, upstream of every stage that could catch it).

    This IS an LLM response model (extra="forbid" so OpenRouter's strict
    json_schema mode has a closed schema to enforce against).
    """

    model_config = ConfigDict(extra="forbid")

    logline: str
    mode: ContentMode
    characters: list[CharacterRef]
    desired_moment: str  # the thing the reaction is begging to see
    why_it_lands: str
    legal_flag: bool  # True = likeness/IP concern to review before render


class IdeaPitchSlate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ideas: list[IdeaPitch] = Field(min_length=2, max_length=3)


# ---------------------------------------------------------------------------
# Ideation stage (PRD ticket 06/D7): the Exilus lane's wide idea slate. This
# is a NEW schema pair, not a widened IdeaPitchSlate in place -- StoryPitcher
# / IdeaPitchSlate stay exactly as they are for the legacy Path A/repitch lane
# (scripts/pitch_angles.py, scripts/repitch_event.py), which the global rules
# forbid breaking. ExilusIdea subclasses IdeaPitch so every pre-existing
# field (logline/mode/characters/desired_moment/why_it_lands/legal_flag)
# reaches StoryArchitect/the craft gate/the writer completely unchanged
# (AC6) -- only target_camp is new.
# ---------------------------------------------------------------------------


class ExilusIdea(IdeaPitch):
    """One idea in an Exilus wide-ideation slate (PRD ticket 06/D7).

    Every ``IdeaPitch`` field is unchanged in name and type -- this is a
    strict addition, not a reshape, so nothing downstream of the pick
    (StoryArchitect, the craft gate, the writer) needs to change (AC6).
    ``target_camp`` is the one new field: the exact ``Camp.name`` (from the
    ``FactionMap`` this idea was built from) the idea targets, which is what
    makes a whole slate's camp coverage externally checkable -- compare the
    set of every idea's ``target_camp`` against the set of camp names in the
    map, never trusted from the model's own say-so alone (``Ideator.generate``
    is what actually checks this in code).
    """

    target_camp: str


class ExilusSlate(BaseModel):
    """The Exilus ideation stage's whole output (PRD ticket 06/D7): a WIDE
    slate of 8-15 :class:`ExilusIdea` entries, replacing ``IdeaPitchSlate``'s
    2-3 for this lane only. The one-camp-per-idea-or-more coverage rule
    cannot be expressed as a schema field bound (a bound only constrains
    total count, not which camp names appear) -- ``Ideator.generate``
    enforces coverage in code after the LLM call.
    """

    model_config = ConfigDict(extra="forbid")

    ideas: list[ExilusIdea] = Field(min_length=8, max_length=15)


def _check_beat_rules(beats: list[StoryBeat]) -> None:
    """Cross-beat craft rules a single-field validator cannot see.

    - Beats must not ALL share one shot_size (forces framing variety — the
      BUG-002 static-shotcraft failure mode).
    - At most one beat may be the hero_moment.

    Shared by ScriptDraft (the architect's raw LLM output) and StoryScript
    (the composed artifact) so the rule cannot drift between them.
    """
    if len({beat.shot_size for beat in beats}) == 1:
        raise ValueError(
            "all beats share one shot_size; vary framing (establish/detail/reveal)"
        )
    hero_count = sum(beat.hero_moment for beat in beats)
    if hero_count > 1:
        raise ValueError(f"at most one hero_moment beat allowed, found {hero_count}")


class ScriptDraft(BaseModel):
    """The StoryArchitect's raw LLM output: staging only, no idea fields.

    The architect is never asked to echo the idea back — logline, mode,
    characters, desired_moment, why_it_lands, and legal_flag are code-copied
    from the picked IdeaPitch into the composed StoryScript (the same
    trust-code-over-LLM doctrine as content_writer's beat-fact copying).
    LLM response model, so extra="forbid".
    """

    model_config = ConfigDict(extra="forbid")

    scene_setting: str
    beats: list[StoryBeat] = Field(min_length=3, max_length=5)

    @model_validator(mode="after")
    def _check_beats(self) -> "ScriptDraft":
        _check_beat_rules(self.beats)
        return self


class StoryScript(BaseModel):
    """The developed story: the picked idea + the architect's staging.

    This is the artifact the craft gate judges, the dialogue floor and
    grounding check read, AnglePitchRecord.story_json persists, and the
    content writer directs from. It carries the exact shape the pre-slice-①
    StoryPitch had MINUS caption_policy/hook_line (dead on-screen-text fields
    of the pre-native-quality-v2 product, deleted with the slim — PRD D11).

    NOT an LLM response model (it is composed in code from IdeaPitch +
    ScriptDraft), so extra="ignore": legacy story_json rows that still carry
    caption_policy/hook_line keys load cleanly and simply drop them.
    """

    model_config = ConfigDict(extra="ignore")

    logline: str
    mode: ContentMode
    characters: list[CharacterRef]
    desired_moment: str  # the thing the reaction is begging to see
    scene_setting: str = ""  # the ONE place/time every beat stays inside; "" = pre-v2 row
    beats: list[StoryBeat] = Field(min_length=3, max_length=5)
    why_it_lands: str
    legal_flag: bool  # True = likeness/IP concern to review before render

    @model_validator(mode="after")
    def _check_beats(self) -> "StoryScript":
        _check_beat_rules(self.beats)
        return self


# Back-compat alias (slice ①, 2026-07-16): every pre-slice consumer that
# type-hinted or validated StoryPitch keeps working against StoryScript —
# same fields minus the deleted caption pair, and extra="ignore" absorbs
# those keys on legacy rows. Migrate imports opportunistically; new code
# says StoryScript.
StoryPitch = StoryScript


class StoryPitchSlate(BaseModel):
    """LEGACY (slice ①): the live loop now emits IdeaPitchSlate (pitcher) and
    a single StoryScript (architect). Only offline ablation scripts
    (run_playbook_ablation.py, run_fridge_phase0.py) still reference this
    shape; they predate the split and crash at runtime against the slim
    pitcher regardless. Kept so their imports resolve; delete with them.
    """

    model_config = ConfigDict(extra="ignore")

    pitches: list[StoryScript] = Field(min_length=2, max_length=3)


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


