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

from collections.abc import Sequence
from pathlib import Path

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

# Reference-render watch items (ticket 10): appended to the checklist only when
# the run carries reference assets. Failure modes from the slice-② research
# brief (RESEARCH-slice2.md §1 hard constraints + the class-specific risk
# PRD-slice2 decision 2 names): ref/render identity mismatch, style bleed
# (08-避坑12问.md:52-60), duplicate-figure twins (08:79-101), and the
# protagonist-summoned-into-frame risk unique to binding a ref to the unseen
# camera-holder.
_REF_WATCH_ITEMS = """- [ ] IDENTITY/COSTUME MATCH — everything on screen that the reference images \
own (limbs, suit detail, mask) matches the source art; costume detail does not drift or \
get reinvented mid-clip.
- [ ] No STYLE BLEED — the reference's art style (vintage grain, illustration flatness, \
render sheen) does not leak into the world's photoreal register.
- [ ] No TWINS — no duplicate or cloned copy of a referenced character anywhere in frame.
- [ ] No SUMMONED PROTAGONIST — the protagonist's referenced character does NOT appear \
as a separate visible figure; refs bind to YOUR limbs only, the camera-holder stays \
unseen."""

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
    ref_paths: Sequence[str | Path] = (),
    prediction_block: str = "",
    probe_exempt: bool = False,
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
        ref_paths: The asset gate's validated reference images in upload
            order (ticket 10). Non-empty → the sheet gains a "Reference
            assets" section listing them in imageN order and the watch
            checklist gains the reference failure modes. Empty → no
            reference-specific content is added (the probe-gate section,
            slice ③, appears on every sheet regardless).
        prediction_block: The verdict module's pre-watch prediction text
            (slice ③, ``verdict.build_prediction_block``) — the ruleset's own
            stated theory, shown above the watch checklist so the operator's
            verdict judges expectations, not vibes. Empty → section omitted
            (older callers/tests).
        probe_exempt: True when this exact compiled prompt already has a
            probe PASS on the lane log (grill Q2c) — the sheet then says so
            and points at the already-released final command instead of
            asking for a redundant probe.

    Returns:
        The full render sheet as a markdown string.
    """
    ref_section: list[str] = []
    if ref_paths:
        ref_section = [
            "## Reference assets (upload order = imageN, ticket 11 binding contract)",
            *[f"- image{i}: {path}" for i, path in enumerate(ref_paths, start=1)],
            "",
        ]
    watch_checklist = (
        f"{_WATCH_CHECKLIST}\n{_REF_WATCH_ITEMS}" if ref_paths else _WATCH_CHECKLIST
    )
    prediction_section: list[str] = []
    if prediction_block:
        prediction_section = ["## Prediction (pre-watch)", prediction_block, ""]
    # Probe gate (slice ③): the sheet carries ONLY the 480p probe command; the
    # final-resolution command is released by logging the probe verdict —
    # `pov.py verdict <run_dir> --pass` writes final_command.txt. A prompt
    # whose exact hash already passed a probe is auto-exempt (grill Q2c).
    if probe_exempt:
        gate_lines = [
            "PROBE ALREADY PASSED for this exact compiled prompt (identical hash on "
            "the lane verdict log) — no re-probe needed; the final command is "
            "released at final_command.txt in this run directory.",
        ]
    else:
        gate_lines = [
            "PROBE GATE: this sheet carries ONLY the 480p probe command. After "
            "watching the probe, log your verdict — a PASS releases the final "
            "command into final_command.txt:",
            "```",
            "uv run python scripts/pov.py verdict <run_dir> --pass --resolution 480p",
            "uv run python scripts/pov.py verdict <run_dir> --fail --resolution 480p "
            "--defect <slug> [--note \"...\"]",
            "```",
            "Deliberate skip (logged as a bypass): add --force-final. Brakes: "
            "2 failed retakes park the story; 150cr per-story cap.",
        ]
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
            *ref_section,
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
            *gate_lines,
            "",
            *prediction_section,
            "## Watch checklist (POV failure modes)",
            watch_checklist,
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
