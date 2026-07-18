"""
POV render sheet builder (ticket 03) — the script's artifacts in, sheet text out.

Composes the human-facing render sheet markdown PRD user story 15 asks for:
the final prompt, a copy-paste CLI command, a cost statement, the MANDATORY
480p->720p->1080p ladder wording, the POV watch checklist (angle switch /
body leak / beat teleport / text leak — PRD user story 17), and the
location-still escalation lever (PRD user story 23). It also carries the
picked pitch's own fields VERBATIM (never re-derived from the script's
authored prose) so a run can be post-mortemed against exactly what the
operator asked for — the "pitch fields byte-identical between operator input
and sheet" code-copy proof this ticket's acceptance criteria names.

Pure function like compiler.compile_pov_prompt: no LLM call, no file I/O —
the driver (scripts/pov.py) writes the returned string to disk.
"""

from src.generation.pov.schemas import CompiledPOVPrompt, POVPitch, POVScript
from src.generation.render_adapters.rules import RenderRules

# Item 1 is the ticket-07 money-shot contract check (first by design — the
# only item that fails the video on its own). Below it, the four POV-specific
# failure modes named in ticket 03, worded from the probe's own watch
# checklist (render_taste_test/pov_probe/PROBE_SHEET.md) and the pov_grammar
# config's evidence trail (unseen_protagonist / anti_drift_constraint),
# rather than reinvented from scratch.
_WATCH_CHECKLIST = """- [ ] MONEY SHOT LANDS — the pitch's stated money_shot image is on screen \
and reads at a glance (item 1 by design, ticket 07: the one question that fails the video \
on its own — if this box is unchecked, the other four passing does not save the take).
- [ ] No ANGLE SWITCH — stays first-person the entire clip; no cut to \
seeing the protagonist from outside, no third-person establishing shot \
(anti_drift_constraint failure).
- [ ] No BODY LEAK — no face, head, shoulders, or body of the protagonist visible in \
frame (the unseen-protagonist device failing).
- [ ] No BEAT TELEPORT — every beat's action visibly animates frame-by-frame in order; \
no hard cut straight from a beat's start-state to its end-state (the BUG-031 motion \
class — render_taste_test/pov_probe/PROBE_SHEET.md probe 2 measured this drawing \
correctly in POV register; confirm it still does on THIS render).
- [ ] No TEXT LEAK — no watermark, logo, subtitles, or on-screen text of any kind."""

# PRD user story 23 / Implementation Decisions "Assets verdict" paragraph — no
# pov_grammar config entry exists for this (ticket 01's scope was the fixed
# prompt clauses + kill list + beat/dialogue/world rules, not this separate
# documented lever), so it is authored directly here.
_LOCATION_STILL_ESCALATION_LEVER = """Text-only worlds are the default and probe-proven \
register for this lane (PRD Implementation Decisions, "Assets verdict") — do NOT reach \
for a reference image just because a watched clip's world reads as bland. The ONE \
pre-registered fix: add ONE location still, framed at EYE VANTAGE (the height/angle the \
unseen protagonist would actually see from — never an establishing shot), named by its \
ROLE in the prose per the positional-binding convention (e.g. "the cave chamber shown in \
the reference image") and never re-described in text once a reference exists — two \
descriptions of the same space fighting on screen is the pitch-51 camera-hijack failure \
this lever exists to avoid. A/B it against the text-only version on its FIRST use before \
treating it as this world's new default."""


def build_render_sheet(
    pitch: POVPitch,
    script: POVScript,
    compiled: CompiledPOVPrompt,
    rules: RenderRules,
) -> str:
    """
    Compose the run's render sheet markdown.

    Args:
        pitch: The picked pitch — embedded verbatim (code-copy proof), never
            re-derived from ``script``'s authored prose.
        script: The developed POVScript — read only for ``duration_seconds``
            and beat count, shown for orientation; the compiled prompt is
            the render truth.
        compiled: The compiler's output for ``script`` (prompt_text,
            cli_command, cost_line).
        rules: The loaded render rules — read once for
            ``scene_lane.retake_ladder``'s wording.

    Returns:
        The full render sheet as a markdown string.
    """
    return "\n".join(
        [
            "# POV Render Sheet",
            "",
            "## Story Pitch (operator input, verbatim)",
            f"- who: {pitch.who}",
            f"- where: {pitch.where}",
            f"- what_happens: {pitch.what_happens}",
            f"- turn: {pitch.turn}",
            f"- money_shot: {pitch.money_shot}",
            "",
            f"Duration: {script.duration_seconds}s ({len(script.beats)} beats, "
            f"{script.camera_register} camera register)",
            "",
            "## Prompt",
            "```",
            compiled.prompt_text,
            "```",
            "",
            "## MANDATORY render ladder",
            f"**{rules.retake_ladder()}**",
            "",
            "480p sanity-pass CLI (copy-paste):",
            "```",
            compiled.cli_command,
            "```",
            "",
            f"Cost: {compiled.cost_line}",
            "",
            "## Watch checklist (POV failure modes)",
            _WATCH_CHECKLIST,
            "",
            "## Location-still escalation lever",
            _LOCATION_STILL_ESCALATION_LEVER,
            "",
            "## Operator corrections (defect log)",
            "One line per gate-2 correction: date, what was wrong, what the operator "
            "changed. RECURRENCE across runs — not a single instance — is what promotes "
            "a defect to a code check or prompt rule (whack-a-mole policy, first live "
            "run 2026-07-17); this log is how recurrence gets measured instead of "
            "remembered.",
            "- (none yet)",
            "",
        ]
    )
