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

from typing import Literal

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
    # The single image the video exists to deliver (ticket 07): thumbnail test
    # (the frame you'd freeze to stop a scroll) + failure test (render nails
    # everything else but misses this = video failed anyway). Exactly one per
    # pitch — one 10-15s continuous take has one peak; two peaks = two videos.
    # REQUIRED, no default (camera_register precedent): an optional field
    # silently reopens the capture gap this ticket exists to close. Idea mode
    # fills it with a placeholder note when --money-shot is not given.
    money_shot: str


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


class POVWorldElement(BaseModel):
    """One declared invented world object's seat-authored identity (D2 ticket 03).

    ``slug`` matches an operator ``--object`` declaration (and its
    ``refs/<slug>/`` directory). ``description`` is the object's visual
    identity in concrete nouns — it is NEVER compiled into the render prompt
    (a bound object's look lives in its reference images; the binding
    sentence substitutes). It exists to feed candidate still generation
    (ticket 04's template prompt) and the run's forensics. Keeping the
    description in a structured field is the grill-Q1 decision: replacing it
    is a field drop, never prose surgery — a lexical strip of world prose
    cannot tell a synonym from a violation (spine-check lesson, 2026-07-15).
    """

    model_config = ConfigDict(extra="forbid")

    slug: str  # matches the --object declaration / refs/<slug>/ directory
    description: str  # concrete visual identity; feeds still generation, never the prompt


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
    # Selects the camera_as_eyes skeleton variant (pov_grammar config): "calm"
    # (probe-proven slight-natural-shake) or "action" (sd-067's hyper-chaotic
    # handheld chain). A Literal, not a free str: an invalid register is a
    # single-field malformed-object defect (same class as the dialogue/speaker
    # pairing above), and OpenRouter's strict json_schema enforces the enum at
    # parse — the cheapest layer that holds it (whack-a-mole policy). REQUIRED,
    # no default: a default would silently re-lock every story to one register,
    # which is exactly the first live run's failure (2026-07-17, calm-locked
    # camera on an action story).
    camera_register: Literal["calm", "action"]
    beats: list[POVBeat]
    world_prose: str  # light/depth-layered nouns/particulates prose (world_prose_craft)
    # One entry per operator-declared --object (D2 ticket 03); [] on runs with
    # no declared objects (every pre-D2 script parses unchanged). Coverage
    # against the declared list is a structural check (craft_enforcement),
    # not a schema validator — the schema can't see the declaration list.
    world_elements: list[POVWorldElement] = []


class CompiledPOVPrompt(BaseModel):
    """The compiler's whole output for one :class:`POVScript`.

    ``prompt_text`` is the final render prompt (fixed clauses + scrubbed
    script prose). ``cli_command`` is a copy-paste Higgsfield CLI invocation
    for the mandatory 480p sanity pass (the POV ladder,
    ``pov_verdict.ladder``) — the final-resolution step is the verdict
    flow's release, not the compiler's. ``cost_line`` is the 480p credit
    estimate from the yaml's measured per-second rate. ``ref_paths`` (D2
    ticket 05) is the bound reference list — see its field comment.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_text: str
    cli_command: str
    cost_line: str
    # The bound reference images, ABSOLUTE paths in upload order (D2 ticket
    # 05): the verdict flow reads these from compiled.json to (a) extend the
    # probe-exemption hash with the ref file names — a ref swap invalidates a
    # prior PASS — and (b) keep the released final command carrying exactly
    # the validated refs. [] on text-only runs (and every pre-D2 artifact).
    ref_paths: list[str] = []
