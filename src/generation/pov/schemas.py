"""Pydantic data contracts for the POV pipeline (slice ①, generic topics only).

.scratch/pov-pipeline/PRD.md is the spec. Three models flow through the
pipeline in order:

- :class:`POVPitch` — the picked pitch (topic mode's slate pick, or the
  operator's ``--idea`` text wrapped verbatim). States who the unseen
  protagonist is, where the scene happens, what happens, and the turn (PRD
  user story 3) — enough to judge a pitch in seconds.
- :class:`POVBeat` / :class:`POVScript` — the script stage's output (ticket
  03/04): scene setting, duration choice, ordered beats, world prose. Story
  facts are CODE-COPIED from the pitch into the script (same
  trust-code-over-LLM doctrine as StoryArchitect,
  ``src/generation/story_architect.py``) — this module does not perform that
  copy itself, it only defines the shapes.
- :class:`CompiledPOVPrompt` — the compiler's output (``compiler.py``): the
  final prompt text, a copy-paste CLI command, and a cost line.

Deliberately UNENFORCED here (ticket 02 scope note): per-beat action count
(1-2), the beat-count budget for the chosen duration, dialogue-never-on-the
-final-beat, and duration in {10, 15}. Those four are cross-beat / whole
-script structural rules that ticket 04 validates together in ONE function
(reading ``RenderRules.pov_grammar()``) so the bounded-repair loop has a
single, consistent violation surface — splitting some of them into Pydantic
validators here and leaving others for ticket 04 would fragment that surface
and make the repair loop harder to reason about. ``duration_seconds`` is
therefore typed ``int``, not ``Literal[10, 15]``, and ``POVBeat.actions`` is
an unconstrained ``list[str]``.

The one validator this module DOES keep is dialogue/speaker pairing on
:class:`POVBeat` — a genuinely single-beat, malformed-object invariant (a
line needs a speaker, a speaker needs a line), not a craft rule. It mirrors
``StoryBeat._check_dialogue_speaker_rule`` in ``src/monitor/schemas.py``
verbatim in shape.
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class POVPitch(BaseModel):
    """One POV story pitch: who you are, where, what happens, and the turn.

    PRD user story 3. In topic mode this is one entry of the pitcher seat's
    3-5 pitch slate (ticket 05); in idea mode it is the operator's
    ``--idea`` text wrapped verbatim into these four fields with no pitcher
    call at all (ticket 03) — either way, every downstream artifact
    code-copies these fields rather than re-deriving them from an LLM echo.
    """

    model_config = ConfigDict(extra="forbid")

    who: str  # the unseen protagonist's identity/role (e.g. "a cave explorer")
    where: str  # the single continuous place the scene happens
    what_happens: str  # the scene's action, in a sentence or two
    turn: str  # the surprise/twist beat the pitch exists to deliver


class POVPitchSlate(BaseModel):
    """Topic mode's pitcher output (ticket 05): a slate of 3-5 distinct POVPitch entries.

    The operator picks ONE by number (``scripts/pov.py``); every pitch,
    picked or not, is persisted to the run directory's ``slate.json`` for
    post-mortem (PRD Testing Decisions / ticket 05 acceptance criteria) —
    the picked entry is additionally code-copied, byte-for-byte, into
    ``pitch.json`` and every downstream artifact rather than re-derived from
    the slate at any later stage.
    """

    model_config = ConfigDict(extra="forbid")

    pitches: list[POVPitch] = Field(min_length=3, max_length=5)


class POVBeat(BaseModel):
    """One beat of a POV script: 1-2 physical actions plus optional dialogue/audio.

    Beats are the compiler's prose-chaining unit (``compiler.py``): the
    compiled prompt's single continuous Action sequence is every beat's
    ``actions`` flattened in order — POV is ONE continuous shot (PRD
    Implementation Decisions), so beats are never rendered as separate cuts
    the way StoryBeat's are.

    ``actions`` and ``audio_events`` are ordered lists rather than one prose
    string so ticket 04's structural check can count actions (≤2 per beat)
    without parsing prose, and so the compiler can join them deterministically
    (no LLM-chosen conjunctions to scrub or trust).
    """

    model_config = ConfigDict(extra="forbid")

    # 1-2 physical actions this beat shows, in order. min_length=1 is structural:
    # an empty-actions beat IS the "beat-free action line" that measurably
    # renders in zero frames (BUG-031 class) — it must never parse, not merely
    # fail a downstream gate (PRD user story 5).
    actions: list[str] = Field(min_length=1)
    audio_events: list[str] = []  # diegetic sound cues co-occurring with this beat
    dialogue_line: str | None = None  # optional spoken line, plain quoted prose
    speaker: str | None = None  # who says dialogue_line; required iff it is set

    @model_validator(mode="after")
    def _check_dialogue_speaker_pair(self) -> "POVBeat":
        """
        dialogue_line and speaker are a pair: both set or both None. A spoken
        line needs a named speaker, and a named speaker with no line is dead
        data. Mirrors ``StoryBeat._check_dialogue_speaker_rule`` (this repo's
        existing convention for the same invariant) — unlike that sibling
        check, there is no on-screen cast list to validate ``speaker``
        against here (POV has no ``characters_in_frame``: the protagonist is
        unseen by construction), so this stops at the pairing itself.
        """
        has_dialogue = self.dialogue_line is not None
        has_speaker = self.speaker is not None
        if has_dialogue != has_speaker:
            raise ValueError(
                "dialogue_line and speaker must both be set or both be None"
            )
        return self


class POVScript(BaseModel):
    """The script stage's output for one picked pitch — the compiler's sole input.

    Fields mirror the PRD's script-stage contract (Implementation Decisions):
    scene setting, duration choice, ordered beats, world prose. Two fields
    exist purely to feed the compiler's fixed clauses (ticket 01's
    ``unseen_protagonist`` config note): ``protagonist_role`` is the short
    noun phrase substituted for the ``[PROTAGONIST]`` token shared by the
    ``camera_as_eyes`` and ``unseen_protagonist`` skeleton clauses (e.g.
    "explorer", "diver"); ``protagonist_detail`` is the trailing gear/pose
    clause the compiler appends after the fixed "Subject: an unseen
    [PROTAGONIST]" fragment (no trailing comma — probe 1 byte pattern), and
    it must carry the hands-visibility phrasing inline
    (``pov_grammar.protagonist_detail_craft``, e.g. "with a headlamp, gloved
    hands occasionally visible at the bottom of frame").

    ``protagonist_role`` is derived from the picked ``POVPitch.who`` by
    whatever composes this script (ticket 03's call — a short substitution
    noun and a free-form "who I am" sentence are not always the same
    string, so that derivation is left open here). It is its own field
    rather than read from a pitch at compile time so the compiler's only
    dependency stays "script in", per the PRD's own framing of the compiler
    seam.
    """

    model_config = ConfigDict(extra="forbid")

    scene_setting: str  # the single continuous place/time every beat happens in
    protagonist_role: str  # substitutes [PROTAGONIST] in the fixed skeleton clauses
    protagonist_detail: str  # trailing gear/pose clause completing the Subject sentence
    duration_seconds: int  # intended 10 or 15; ticket 04 validates + bounded-repairs
    beats: list[POVBeat]
    world_prose: str  # light/depth-layered nouns/particulates prose (world_prose_craft)


class CompiledPOVPrompt(BaseModel):
    """The compiler's whole output for one :class:`POVScript`.

    ``prompt_text`` is the final render prompt (fixed clauses + scrubbed
    script prose). ``cli_command`` is a copy-paste Higgsfield CLI invocation
    for the mandatory 480p sanity pass (retake_ladder,
    ``config/render_rules.yaml``) — the 720p/1080p ladder steps are the
    render sheet's job (ticket 03), not the compiler's. ``cost_line`` is the
    480p credit estimate from the yaml's measured per-second rate.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_text: str
    cli_command: str
    cost_line: str
