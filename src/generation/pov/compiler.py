"""POV prompt compiler (ticket 02) — script in, final prompt text out.

Deterministic code, never an LLM (PRD Implementation Decisions): the fixed
POV skeleton clauses (ticket 01, ``config/render_rules.yaml``'s
``pov_grammar`` block) are injected byte-verbatim so the load-bearing
grammar — camera-IS-eyes, the unseen-protagonist device,
"No cuts, no zooms, natural head movement only", the constraints block — can
never drift with LLM phrasing (PRD user story 13). Hands-visibility is NOT a
fixed clause: the probes express it inline in the script-authored Subject:
detail (``pov_grammar.protagonist_detail_craft``), enforced at the
script-writer prompt level. Everything the script
stage authored (protagonist detail, beat actions/dialogue, world prose) is
scrubbed of kill-list vocabulary and bracketed timestamps BEFORE it is
spliced next to a fixed clause, so scrubbing can never touch — and drift —
the fixed text itself (PRD user story 14; the ``[PROTAGONIST]`` token is
substituted into the fixed clauses separately, before any scrub, so the
bracket-stripping pass below never sees it).

Composition order (mirrors the probe-proven structure,
``render_taste_test/pov_probe/PROBE_SHEET.md``, without requiring the script
stage to author separately-labelled Scene/Light/Style fields the PRD's
script-stage contract never names):

    camera_as_eyes -> Subject (unseen_protagonist + protagonist_detail; the
    detail carries hands-visibility inline per
    pov_grammar.protagonist_detail_craft — there is NO standalone hands
    clause, the slice-1 verifier killed that as probe-unvalidated) ->
    Action, in order (beats flattened, dialogue interleaved at its beat's
    position) -> Scene -> World -> anti_drift_constraint -> Audio (beats'
    audio events, "no music" per the seedance dialect's audio_rule) ->
    constraints_block

Deliberately OUT of this module's scope (ticket 04): dialogue-never-final
-beat, per-beat action count, the beat-count budget, duration in {10, 15} —
those are cross-beat/whole-script structural rules validated together with a
bounded-repair loop, not this pure function's job. This module raises only
on the word-budget target, which is genuinely this compiler's own
responsibility (PRD user story 9/Testing Decisions: "word budget respected"
is a seam-2 assertion, and nothing else in the pipeline checks it).
"""

import re

from src.generation.executor import _sanitize_prompt
from src.generation.pov.schemas import CompiledPOVPrompt, POVScript
from src.generation.render_adapters.rules import RenderRules

# --- CLI / cost constants ----------------------------------------------------
# The 480p sanity pass only (retake_ladder, config/render_rules.yaml) — the
# 720p/1080p ladder steps belong on the render sheet (ticket 03), not here.
_SANITY_RESOLUTION = "480p"
_ASPECT_RATIO = "9:16"

_BRACKET_RE = re.compile(r"\[[^\]]*\]")


class POVWordBudgetError(ValueError):
    """Raised when the compiled body falls outside the config's word-budget target.

    "Body" is everything the script stage authored — protagonist detail,
    scene setting, world prose, and every beat's actions/dialogue/audio —
    EXCLUDING the fixed skeleton clauses and the constraints block, per
    ``pov_grammar.world_prose_craft.body_word_target.excludes``. A script
    this far outside the corpus-sourced 60-100 word range is a script-stage
    defect, not something this compiler should silently accept or pad.
    """


def _ensure_terminal_period(text: str) -> str:
    """Guarantee ``text`` ends with sentence-terminal punctuation.

    ``subject_sentence`` and ``world_sentence`` are spliced directly before
    the next sentence (``Action, in order:`` / ``anti_drift_constraint``)
    with only a single space between them (the ``" ".join(...)`` in
    :func:`compile_pov_prompt`). Script-authored prose
    (``protagonist_detail`` / ``world_prose``) is not guaranteed to end in a
    period — when it doesn't, the two sentences run together unpunctuated,
    which reads as a single garbled clause rather than two sentences to both
    a human proofreading the sheet and the render model reading the prompt.
    A no-op when the text already ends in ``.``/``!``/``?``.
    """
    if text and not text.endswith((".", "!", "?")):
        return f"{text}."
    return text


def _sub_protagonist(text: str, role: str) -> str:
    """Substitute the shared ``[PROTAGONIST]`` bracket token with ``role``.

    Applied to the fixed skeleton-clause text BEFORE any prose scrub, so the
    generic bracket-stripping pass in :func:`_scrub` never sees — and can
    never eat — this one legitimate bracket token.
    """
    return text.replace("[PROTAGONIST]", role)


def _scrub(text: str, kill_list: dict) -> str:
    """Scrub kill-list vocabulary and any bracketed content from one LLM-authored field.

    Applied to EACH script-authored string individually, before it is
    spliced next to any fixed clause (never to the fully-assembled prompt) —
    this is what keeps the fixed clauses byte-exact while still guaranteeing
    kill-list words and bracket tokens can never survive regardless of where
    in the script's prose they appeared.

    Three passes:
      1. Bracketed timestamps (or any bracketed content) — stripped
         unconditionally. Higgsfield rejects bracketed timelines at any
         duration >5s (seedance_2_0.dialect.bracket_ban); a compiler whose
         whole purpose is keeping documented render-killers off a paid
         render cannot leave this to prompt discipline.
      2. Dead intensifiers + bare "cinematic" — removed as whole words.
         Config's ``cinematic_without_specifics`` carves out a paired usage
         ("cinematic film tone, 35mm, golden hour") as legitimate, but that
         word never appears in any POV probe or corpus example for this
         lane; the safe simplification is a blanket scrub rather than a
         comma-proximity heuristic that could false-negative on a paid
         render. # ponytail: blanket cinematic scrub, no paired-usage
         carve-out; revisit if a real script legitimately wants it.
      3. glow / glimmer — replaced with their configured steady-intensity
         substitutes (flicker/strobe cue avoidance, probe-observed).
    """
    cleaned = _BRACKET_RE.sub("", text)

    words_to_drop = set(kill_list["dead_intensifiers"]["words"])
    words_to_drop.add(kill_list["cinematic_without_specifics"]["word"])
    for word in words_to_drop:
        cleaned = re.sub(rf"\b{re.escape(word)}\b", "", cleaned, flags=re.IGNORECASE)

    for banned, replacement in kill_list["glow_glimmer"]["replace"].items():
        cleaned = re.sub(rf"\b{re.escape(banned)}\b", replacement, cleaned, flags=re.IGNORECASE)

    # Collapse the whitespace/punctuation debris the word-removal passes leave
    # behind (e.g. "a stunning, breathtaking view" -> "a ,  view" -> "a view").
    cleaned = re.sub(r"\s*,\s*,", ",", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r",\s*\.", ".", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^,\s*", "", cleaned)
    return cleaned


def _flatten_actions(script: POVScript) -> tuple[list[str], list[str]]:
    """Flatten every beat's actions/dialogue and audio events into two ordered lists.

    POV is ONE continuous shot (no per-beat cuts), so beats are joined as a
    single flowing action sequence rather than StoryArchitect's "Then cut
    to:" multi-shot chaining. A beat's dialogue line is interleaved into the
    action sequence at that beat's position (spoken lines are part of what
    happens in order, not a separate list) since the script/beat model
    carries no per-beat timestamp for the compiler to place it by otherwise.
    """
    action_items: list[str] = []
    audio_items: list[str] = []
    for beat in script.beats:
        action_items.extend(beat.actions)
        if beat.dialogue_line is not None:
            action_items.append(f'{beat.speaker} says, "{beat.dialogue_line}"')
        audio_items.extend(beat.audio_events)
    return action_items, audio_items


def compile_pov_prompt(script: POVScript, rules: RenderRules) -> CompiledPOVPrompt:
    """Compile a :class:`POVScript` into the final prompt text, CLI command, and cost line.

    Pure function: everything it needs comes from ``script`` and ``rules``
    (which itself is a read-once in-memory view over the committed yaml, not
    a live file read per call). No LLM call, no network, no render.

    Raises:
        POVWordBudgetError: if the compiled body's word count falls outside
            ``pov_grammar.world_prose_craft.body_word_target``.
    """
    grammar = rules.pov_grammar()
    clauses = grammar["skeleton_clauses"]
    kill_list = grammar["kill_list"]
    budget = grammar["world_prose_craft"]["body_word_target"]
    role = script.protagonist_role

    camera_as_eyes = _sub_protagonist(clauses["camera_as_eyes"]["text"], role)
    unseen_protagonist = _sub_protagonist(clauses["unseen_protagonist"]["text"], role)
    anti_drift = clauses["anti_drift_constraint"]["text"]
    constraints_block = clauses["constraints_block"]["text"]

    protagonist_detail = _scrub(script.protagonist_detail, kill_list)
    scene_setting = _scrub(script.scene_setting, kill_list)
    world_prose = _scrub(script.world_prose, kill_list)
    action_items, audio_items = _flatten_actions(script)
    action_items = [_scrub(item, kill_list) for item in action_items]
    audio_items = [_scrub(item, kill_list) for item in audio_items]

    body_word_count = sum(
        len(part.split())
        for part in [protagonist_detail, scene_setting, world_prose, *action_items, *audio_items]
    )
    if not (budget["min_words"] <= body_word_count <= budget["max_words"]):
        raise POVWordBudgetError(
            f"compiled body is {body_word_count} words; "
            f"target is {budget['min_words']}-{budget['max_words']} "
            f"(excludes fixed skeleton clauses and the constraints block)"
        )

    subject_sentence = _ensure_terminal_period(
        f"{unseen_protagonist} {protagonist_detail}".strip()
    )
    action_sentence = f"Action, in order: {'; '.join(action_items)}."
    scene_sentence = f"Scene: {scene_setting}."
    world_sentence = _ensure_terminal_period(f"World: {world_prose}")
    # Empty audio_items (no beat authored an audio event) must not compose into
    # "Audio: , no music." — a malformed leading comma reaching a paid render.
    closing_term = grammar["audio_rule"]["closing_term"]
    audio_sentence = f"Audio: {', '.join([*audio_items, closing_term])}."

    prompt_text = " ".join(
        [
            camera_as_eyes,
            subject_sentence,
            action_sentence,
            scene_sentence,
            world_sentence,
            anti_drift,
            audio_sentence,
            constraints_block,
        ]
    )
    prompt_text = re.sub(r"\s+", " ", prompt_text).strip()

    model_id = rules.scene_model()
    # Loud, named failure over a bare KeyError: the sheet PROMISES a cost (L7
    # cost-governance), so an unmeasured sanity-tier rate must halt compilation
    # with the missing config key spelled out — never silently re-rate at
    # another tier (executor's 720p fallback is the wrong semantic here).
    try:
        rate = rules.model(model_id)["limits"]["cost_estimate_credits"][
            f"per_second_{_SANITY_RESOLUTION}"
        ]
    except KeyError as exc:
        raise ValueError(
            f"no measured {_SANITY_RESOLUTION} rate for {model_id} in "
            f"render_rules.yaml limits.cost_estimate_credits — the render sheet "
            f"cannot state a cost (L7) without it"
        ) from exc
    cost = script.duration_seconds * rate
    # _sanitize_prompt (src/generation/executor.py) strips the shell-hostile
    # characters the Windows .cmd-shim CreateProcess quirk can't reliably
    # escape (module docstring there) — reused here ONLY for the copy-paste
    # CLI string; prompt_text itself stays untouched/readable.
    cli_command = (
        f'higgsfield generate create {model_id} --prompt "{_sanitize_prompt(prompt_text)}" '
        f"--aspect_ratio {_ASPECT_RATIO} --duration {script.duration_seconds} "
        f"--resolution {_SANITY_RESOLUTION} --wait"
    )
    cost_line = (
        f"{_SANITY_RESOLUTION} sanity render: {script.duration_seconds}s x {rate}cr/s = {cost}cr"
    )

    return CompiledPOVPrompt(
        prompt_text=prompt_text,
        cli_command=cli_command,
        cost_line=cost_line,
    )
