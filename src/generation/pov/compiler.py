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
    position) -> Scene -> World -> anti_drift_constraint ->
    continuous_take_constraint (doc 15:385's second angle-switch guard —
    promoted 2026-07-17 after the kaiju run watched an ANGLE SWITCH with
    anti_drift alone, then passed 3/3 watches with both) -> style_register
    (fixed Style: clause selected by camera_register — both probes carry it,
    the original transcription missed it, BUG-033) -> Audio (beats' audio
    events, "no music" per the seedance dialect's audio_rule) ->
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
from collections.abc import Sequence

from src.generation.executor import _sanitize_prompt
from src.generation.pov.asset_check import ResolvedCharacter
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
    this far outside the duration-keyed corpus-sourced range (60-100 @10s,
    60-120 @15s — the ``at_<duration>s`` rows, BUG-036) is a script-stage
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


def _apply_replace_table(text: str, table: dict[str, str]) -> str:
    """Replace each table key with its phrase — whole word, case-insensitive.

    The shared mechanic behind the glow/glimmer and sensitive-actions passes
    (both are word→phrase config tables applied identically).
    """
    for banned, replacement in table.items():
        text = re.sub(rf"\b{re.escape(banned)}\b", replacement, text, flags=re.IGNORECASE)
    return text


def _scrub(text: str, kill_list: dict) -> str:
    """Scrub kill-list vocabulary and any bracketed content from one LLM-authored field.

    Applied to EACH script-authored string individually, before it is
    spliced next to any fixed clause (never to the fully-assembled prompt) —
    this is what keeps the fixed clauses byte-exact while still guaranteeing
    kill-list words and bracket tokens can never survive regardless of where
    in the script's prose they appeared.

    Four passes:
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
      4. Filter-risk action words (fight/battle/destroy, kill/brutal/attack,
         punch/slash, blood) — replaced with the doc-19 §3 corpus phrases
         (``kill_list.sensitive_actions``, ticket 08). Bare documented forms
         only: inflections pass through by design (extending beyond the
         table would be a self-invented technique; see the config row's
         evidence note).
    """
    cleaned = _BRACKET_RE.sub("", text)

    words_to_drop = set(kill_list["dead_intensifiers"]["words"])
    words_to_drop.add(kill_list["cinematic_without_specifics"]["word"])
    for word in words_to_drop:
        cleaned = re.sub(rf"\b{re.escape(word)}\b", "", cleaned, flags=re.IGNORECASE)

    cleaned = _apply_replace_table(cleaned, kill_list["glow_glimmer"]["replace"])
    cleaned = _apply_replace_table(cleaned, kill_list["sensitive_actions"]["replace"])

    # Collapse the whitespace/punctuation debris the word-removal passes leave
    # behind (e.g. "a stunning, breathtaking view" -> "a ,  view" -> "a view").
    cleaned = re.sub(r"\s*,\s*,", ",", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = re.sub(r",\s*\.", ".", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^,\s*", "", cleaned)
    return cleaned


def _normalize_fragment(text: str, kill_list: dict) -> str:
    """Scrub one LLM-authored fragment AND strip its trailing period/whitespace.

    THE punctuation contract for every splice point: the compiler owns ALL
    punctuation between fragments — sentence builders append their own
    terminal '.' (via :func:`_ensure_terminal_period` or a literal), joiners
    own the '; '/', ' between list items. LLM prose arrives with or without
    trailing periods roll-to-roll; normalizing here (rather than guarding
    each seam individually) is the class fix for the recurring defect family:
    subject/world run-ons (ticket 03), 'Scene: ...figures..' (first kaiju
    rerun), and 'steel.;' / 'glass.,' / 'camera..' item joins (beam rerun) —
    four same-class instances, 2026-07-17. Trailing '!'/'?' are left alone
    (meaningful, and _ensure_terminal_period treats them as terminal).
    """
    return _scrub(text, kill_list).rstrip(". ")


def count_body_words(script: POVScript) -> int:
    """Count the script-authored body words the duration-keyed budget governs.

    Counts RAW (pre-scrub) text: protagonist detail, scene setting, world
    prose, and every beat's actions, dialogue lines, and audio events —
    excluding the fixed skeleton clauses and constraints block, per
    ``pov_grammar.world_prose_craft.body_word_target.excludes``. Shared by
    this compiler's hard backstop and ``craft_enforcement``'s repairable
    budget check so the two can never disagree on what "body" means. The
    compiler's own post-scrub count can only be <= this one (scrubbing only
    removes words), so a script passing here cannot fail the backstop's
    lower bound spuriously — and an over-budget raw script is a script-stage
    defect regardless of what scrubbing might shave off.
    """
    parts = [script.protagonist_detail, script.scene_setting, script.world_prose]
    for beat in script.beats:
        parts.extend(beat.actions)
        parts.extend(beat.audio_events)
        if beat.dialogue_line is not None:
            parts.append(beat.dialogue_line)
    return sum(len(part.split()) for part in parts)


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


def _binding_sentences(
    bound_characters: Sequence[ResolvedCharacter],
    grammar: dict,
    protagonist_role: str,
) -> list[str]:
    """Compose one positional binding sentence per bound character, in upload order.

    Templates come from ``pov_grammar.ip_binding`` (ticket 11): the
    protagonist form is the probe-frozen wording (ip_probe roll 1b, user
    watch PASS — arms bound to the refs, NO summoned figure), the in_frame
    form is the scene-lane's measured visible-character sentence. The
    ``imageN`` counter runs continuously across characters in the SAME order
    the CLI ``--image`` flags are emitted (both derive from
    ``bound_characters``), so numbering can never drift from upload order.
    in_frame characters are named by their slug with underscores as spaces —
    the prompt needs a readable noun, and the slug is the only name the
    pipeline has for them.
    """
    sentences: list[str] = []
    next_image = 1
    for character in bound_characters:
        image_list = ", ".join(
            f"image{n}" for n in range(next_image, next_image + len(character.ref_paths))
        )
        next_image += len(character.ref_paths)
        template = grammar["ip_binding"][character.role]["text"]
        text = template.replace("{image_list}", image_list)
        if character.role == "protagonist":
            text = text.replace("[PROTAGONIST]", protagonist_role)
        else:
            text = text.replace("[NAME]", character.slug.replace("_", " "))
        sentences.append(text)
    return sentences


def compile_pov_prompt(
    script: POVScript,
    rules: RenderRules,
    bound_characters: Sequence[ResolvedCharacter] = (),
) -> CompiledPOVPrompt:
    """Compile a :class:`POVScript` into the final prompt text, CLI command, and cost line.

    Pure function: everything it needs comes from ``script`` and ``rules``
    (which itself is a read-once in-memory view over the committed yaml, not
    a live file read per call). No LLM call, no network, no render.

    ``bound_characters`` (tickets 10+11) are the asset gate's validated
    canon subjects in upload order. Each contributes (a) one positional
    binding sentence spliced directly after the Subject sentence — the
    probe-frozen wording for the protagonist role, the scene-lane measured
    form for in_frame — and (b) its reference paths as ``--image`` flags on
    the CLI command. Both derive from the same sequence, so the ``imageN``
    numbering and the upload order can never disagree. The CLI auto-uploads
    plain paths for seedance_2_0 (executor.py, measured 2026-07-06). Empty
    (the default) compiles byte-identically to the slice-① output.

    Raises:
        POVWordBudgetError: if the compiled body's word count falls outside
            ``pov_grammar.world_prose_craft.body_word_target``.
    """
    grammar = rules.pov_grammar()
    clauses = grammar["skeleton_clauses"]
    kill_list = grammar["kill_list"]
    # Duration-keyed row (BUG-036) — a direct index, loud KeyError on an
    # out-of-contract duration: the craft gate upstream owns duration
    # validity (craft_enforcement._VALID_DURATIONS).
    budget = grammar["world_prose_craft"]["body_word_target"][
        f"at_{script.duration_seconds}s"
    ]
    role = script.protagonist_role

    # camera_as_eyes carries register variants (calm/action) — the script's
    # camera_register (a Literal, schema-enforced) picks which fixed clause
    # opens the prompt (first live run 2026-07-17: one calm-locked clause for
    # every story flatlined action stories).
    camera_as_eyes = _sub_protagonist(
        clauses["camera_as_eyes"][script.camera_register]["text"], role
    )
    unseen_protagonist = _sub_protagonist(clauses["unseen_protagonist"]["text"], role)
    anti_drift = clauses["anti_drift_constraint"]["text"]
    # Second camera guard for the same angle-switch class: the 2026-07-17
    # kaiju run watched an angle switch with anti_drift alone present.
    continuous_take = clauses["continuous_take_constraint"]["text"]
    # Style rides the same register axis as the camera (grill decision
    # 2026-07-17) — both probes carry a Style: sentence the original grammar
    # transcription missed (BUG-033: the styleless kaiju render watched as
    # "not realistic or cinematic").
    style_clause = clauses["style_register"][script.camera_register]["text"]
    constraints_block = clauses["constraints_block"]["text"]

    protagonist_detail = _normalize_fragment(script.protagonist_detail, kill_list)
    scene_setting = _normalize_fragment(script.scene_setting, kill_list)
    world_prose = _normalize_fragment(script.world_prose, kill_list)
    action_items, audio_items = _flatten_actions(script)
    action_items = [_normalize_fragment(item, kill_list) for item in action_items]
    audio_items = [_normalize_fragment(item, kill_list) for item in audio_items]

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
    # Binding sentences (ticket 11) sit directly after the Subject sentence —
    # the probe roll-1b byte pattern. Fixed config templates, never scrubbed.
    binding_block = _binding_sentences(bound_characters, grammar, role)
    # Every builder ends its sentence via _ensure_terminal_period — fragments
    # arrive period-stripped from _normalize_fragment (the punctuation
    # contract lives on that helper's docstring).
    action_sentence = _ensure_terminal_period(f"Action, in order: {'; '.join(action_items)}")
    scene_sentence = _ensure_terminal_period(f"Scene: {scene_setting}")
    world_sentence = _ensure_terminal_period(f"World: {world_prose}")
    # Empty audio_items (no beat authored an audio event) must not compose into
    # "Audio: , no music." — a malformed leading comma reaching a paid render.
    closing_term = grammar["audio_rule"]["closing_term"]
    audio_sentence = _ensure_terminal_period(f"Audio: {', '.join([*audio_items, closing_term])}")

    prompt_text = " ".join(
        [
            camera_as_eyes,
            subject_sentence,
            *binding_block,
            action_sentence,
            scene_sentence,
            world_sentence,
            anti_drift,
            continuous_take,
            style_clause,
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
    all_ref_paths = [path for character in bound_characters for path in character.ref_paths]
    ref_flags = "".join(f' --image "{path}"' for path in all_ref_paths)
    cli_command = (
        f'higgsfield generate create {model_id} --prompt "{_sanitize_prompt(prompt_text)}" '
        f"--aspect_ratio {_ASPECT_RATIO} --duration {script.duration_seconds} "
        f"--resolution {_SANITY_RESOLUTION}{ref_flags} --wait"
    )
    cost_line = (
        f"{_SANITY_RESOLUTION} sanity render: {script.duration_seconds}s x {rate}cr/s = {cost}cr"
    )

    return CompiledPOVPrompt(
        prompt_text=prompt_text,
        cli_command=cli_command,
        cost_line=cost_line,
    )
