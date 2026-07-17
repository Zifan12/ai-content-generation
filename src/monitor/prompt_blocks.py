"""Shared tagged-data prompt blocks for the story stages.

The pitcher (src/monitor/story_pitcher.py) and the architect
(src/generation/story_architect.py) both inject the trending event and the
gap analysis into their prompts as tagged data blocks. The rendering lives
here once so the two stages can never drift on the block format — both
prompts promise the model an <event>/<gap> tag, and this module is what
makes that promise true.

``brief_block``/``faction_block`` (PRD ticket 06/D7) are the Exilus lane's
equivalent pair for the Ideator stage (src/monitor/ideation.py), which reads
ONLY the two pinned Exilus artifacts (TopicBrief, FactionMap) -- no event,
no gap analysis -- so they render those two schemas instead.
"""

from src.monitor.schemas import FactionMap, GapAnalysis, TopicBrief, TrendingEvent


def gap_block(gap: GapAnalysis) -> str:
    """Render the gap analysis as a tagged <gap> data block."""
    return (
        "<gap>\n"
        f"dominant_emotion: {gap.dominant_emotion}\n"
        f"audience_want: {gap.audience_want}\n"
        f"evidence_quotes: {gap.evidence_quotes}\n"
        f"reasoning: {gap.reasoning}\n"
        "</gap>"
    )


def event_block(event: TrendingEvent) -> str:
    """Render the trending event as a tagged <event> data block."""
    return (
        "<event>\n"
        f"headline: {event.headline}\n"
        f"audience_reaction: {event.reaction_sample}\n"
        "</event>"
    )


def brief_block(brief: TopicBrief) -> str:
    """Render a Topic Brief as a tagged <brief> data block (Exilus ticket 06).

    Each of the four checked fields is suffixed ``[UNVERIFIED]`` when its
    ``verified`` flag is False -- the checker-exhaustion halt path (ticket
    03/04) stamps this per field, so a stage reading this block sees exactly
    which claims are still unconfirmed rather than a blanket flag on the
    whole brief. Citations are deliberately NOT rendered here: they matter to
    the brief checker (grounding a citation against the gathered URL set),
    not to ideation, which only needs the facts themselves.
    """
    checked_fields = (
        ("identity", brief.identity),
        ("recent_events", brief.recent_events),
        ("key_characters", brief.key_characters),
        ("why_people_care", brief.why_people_care),
    )
    lines = ["<brief>"]
    for name, field in checked_fields:
        stamp = " [UNVERIFIED]" if not field.verified else ""
        lines.append(f"{name}{stamp}: {field.content}")
    if brief.open_unknowns:
        lines.append("open_unknowns:")
        lines.extend(f"- {unknown}" for unknown in brief.open_unknowns)
    lines.append("</brief>")
    return "\n".join(lines)


def faction_block(faction_map: FactionMap) -> str:
    """Render a Faction Map as a tagged <faction_map> data block (Exilus ticket 06).

    Lists every camp with exactly the fields ideation needs to write a
    distinct, on-target idea per camp: ``name`` (the exact string an idea
    must echo back verbatim as its ``target_camp``), ``feeling``,
    ``surface_want`` (the audience's own words), ``deeper_desire`` (labeled
    inferred, never printed as a settled fact), and ``weight``. A
    ``thin_data`` map is prefixed with a note so the model does not
    over-commit to camps built on thin evidence.
    """
    lines = ["<faction_map>"]
    if faction_map.thin_data:
        lines.append(
            "(THIN DATA: built on fewer surviving comments than the usual "
            "floor -- treat weights as rough, not precise.)"
        )
    for camp in faction_map.camps:
        lines.append(
            f"- name: {camp.name} | weight: {camp.weight:.2f} | feeling: {camp.feeling}\n"
            f"  surface_want: {camp.surface_want}\n"
            f"  deeper_desire (inferred, not confirmed): {camp.deeper_desire}"
        )
    lines.append("</faction_map>")
    return "\n".join(lines)
