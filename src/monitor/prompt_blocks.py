"""Shared tagged-data prompt blocks for the story stages.

The pitcher (src/monitor/story_pitcher.py) and the architect
(src/generation/story_architect.py) both inject the trending event and the
gap analysis into their prompts as tagged data blocks. The rendering lives
here once so the two stages can never drift on the block format — both
prompts promise the model an <event>/<gap> tag, and this module is what
makes that promise true.
"""

from src.monitor.schemas import GapAnalysis, TrendingEvent


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
