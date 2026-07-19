"""POV script structural validation + bounded repair (ticket 04).

PRD Implementation Decisions ("Script stage contract"): four cross-beat /
whole-script structural rules are validated together, IN CODE, never left to
the LLM's own judgment or to a downstream LLM judge (PRD Implementation
Decisions, "Human gates only" — slice ① has no LLM craft judge at all):

    1. duration_seconds is 10 or 15.
    2. the beat count fits that duration's budget (4-6 @10s, 5-8 @15s,
       ``pov_grammar.beat_budget``).
    3. every beat carries at most 2 actions.
    4. the LAST beat never carries a dialogue_line (the documented
       end-of-clip audio-artifact zone, ``pov_grammar.dialogue_rules``).

``check_structure`` is the pure seam-2-style function (mirrors
``compiler.compile_pov_prompt``: script + rules in, no LLM, no I/O) that
names every violation found. ``develop_valid_script`` is the seam-1-style
bounded-repair orchestration ticket 03's driver (``scripts/pov.py``)
deliberately left undone: ONE repair re-call targeted at the script seat
ONLY (the pitch is never regenerated — PRD: "Repair prompts re-target the
script seat only"), then a loud, typed failure if the violation persists —
never a silent pass-through of a structurally broken script into the
compiler.
"""

from src.generation.pov.compiler import count_body_words
from src.generation.pov.schemas import POVPitch, POVScript
from src.generation.render_adapters.rules import RenderRules

_MAX_ACTIONS_PER_BEAT = 2
_VALID_DURATIONS = (10, 15)


class POVStructuralViolationError(ValueError):
    """Raised when a POVScript still violates structural rules after one repair.

    The house bounded-retry convention (mirrors ``StoryArchitect.repair``'s
    single-shot pattern, ``src/generation/story_architect.py``): a violation
    gets exactly one named repair attempt, and if it persists this is raised
    with every surviving violation listed — a hard, loud failure, never a
    silent pass-through of a broken script into the compiler.
    """


def check_structure(script: POVScript, rules: RenderRules) -> list[str]:
    """
    Check ``script`` against the four structural rules and return every violation found.

    Pure function: no LLM call, no I/O. An empty list means the script is
    structurally valid. Each violation is a human- and LLM-readable sentence
    naming exactly what is wrong, suitable for both a hard-fail error message
    and a repair prompt's ``<violations>`` block.

    Args:
        script: The script to check.
        rules: A loaded RenderRules instance — read once for
            ``pov_grammar()["beat_budget"]``.

    Returns:
        A list of violation strings, in the order: duration, beat-count
        budget (only checked when duration is valid — an invalid duration
        has no budget to check against), per-beat action count (one entry
        per offending beat), final-beat dialogue.
    """
    beat_budget = rules.pov_grammar()["beat_budget"]
    violations: list[str] = []

    if script.duration_seconds not in _VALID_DURATIONS:
        violations.append(
            f"duration_seconds must be 10 or 15, got {script.duration_seconds}"
        )
    else:
        budget = beat_budget[f"at_{script.duration_seconds}s"]
        beat_count = len(script.beats)
        if not (budget["min"] <= beat_count <= budget["max"]):
            violations.append(
                f"beat count is {beat_count}; the {script.duration_seconds}s budget is "
                f"{budget['min']}-{budget['max']} beats"
            )

    for index, beat in enumerate(script.beats):
        if len(beat.actions) > _MAX_ACTIONS_PER_BEAT:
            violations.append(
                f"beat {index} has {len(beat.actions)} actions; "
                f"at most {_MAX_ACTIONS_PER_BEAT} are allowed per beat"
            )

    if script.beats and script.beats[-1].dialogue_line is not None:
        violations.append(
            "the last beat carries a dialogue_line; dialogue must never land on the final beat"
        )

    # Word budget joins the repairable set (first live run 2026-07-17: a
    # 318-word body died at the compiler's hard backstop with no repair
    # chance — a budget breach is exactly the kind of named, fixable defect
    # the bounded repair exists for). Shares the compiler's own counter so
    # the two layers can never disagree on what "body" means.
    word_budget = rules.pov_grammar()["world_prose_craft"]["body_word_target"]
    body_words = count_body_words(script)
    if not (word_budget["min_words"] <= body_words <= word_budget["max_words"]):
        violations.append(
            f"the authored body totals {body_words} words; the word budget is "
            f"{word_budget['min_words']}-{word_budget['max_words']} combined across "
            f"protagonist detail, scene setting, world prose, and every beat's "
            f"action/dialogue/audio text — cut or expand to fit"
        )

    return violations


def develop_valid_script(
    script_writer,
    pitch: POVPitch,
    rules: RenderRules,
    ref_bound: tuple[str, ...] = (),
) -> POVScript:
    """
    Develop ``pitch`` into a structurally valid POVScript, with one bounded repair.

    Flow: ``script_writer.develop(pitch)`` -> :func:`check_structure`. Clean
    on the first pass -> return immediately, zero repair calls (the ticket's
    "valid scripts pass through with zero repair calls" acceptance
    criterion). Any violation -> exactly ONE ``script_writer.repair(pitch,
    script, violations)`` call, re-checked; a violation surviving THAT
    re-check raises :class:`POVStructuralViolationError` naming every
    surviving violation — hard fail, never silent pass-through.

    Args:
        script_writer: Anything with ``develop(pitch) -> POVScript`` and
            ``repair(pitch, failed_script, violations) -> POVScript`` (real:
            ``POVScriptWriter``; tests: a fake recording calls). Duck-typed
            rather than given a Protocol — matches this pipeline's existing
            ``run_pov_pipeline`` convention (``scripts/pov.py``) for the same
            parameter.
        pitch: The picked pitch — passed to both ``develop`` and ``repair``
            unchanged; the pitch is never regenerated (PRD Implementation
            Decisions).
        rules: A loaded RenderRules instance, passed through to
            :func:`check_structure`.
        ref_bound: Slugs of ref-bound canon subjects (ticket 11), passed
            through unchanged to both ``develop`` and ``repair`` so the
            appearance-ownership rule applies on the repair call too.

    Returns:
        A structurally valid POVScript.

    Raises:
        POVStructuralViolationError: if a violation survives the one bounded
            repair attempt.
    """
    script = script_writer.develop(pitch, ref_bound=ref_bound)
    violations = check_structure(script, rules)
    if not violations:
        return script

    script = script_writer.repair(pitch, script, violations, ref_bound=ref_bound)
    violations = check_structure(script, rules)
    if violations:
        raise POVStructuralViolationError(
            "POV script failed structural validation after one bounded repair: "
            + "; ".join(violations)
        )
    return script
