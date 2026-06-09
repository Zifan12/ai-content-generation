"""
Render a ContentPackage into the flat text the writer-judge reads (v1 eval).

PURE: premise + package in, string out. No LLM, no I/O — so it is unit-testable
with plain assertions. The WriterJudge (Task 7) takes this string, wraps it with
the anchored rubric + system prompt, and makes the Opus call. The seam is
deliberate: assembling text is cheap/testable here; the paid LLM call lives there.

The format below foregrounds premise + organizing_principle at the top (they
condition the premise_fidelity and principle_execution dimensions) and emits one
labeled block per shot so the three beats do not smear together.

FORMAT TEMPLATES are provided (str.format-style). The render logic — reading the
package fields, looping the shots, guarding the optional end_keyframe, filling and
joining the templates — is the function body you write.
"""

from src.schemas.generation import ContentPackage


# Top-level brief. {shot_blocks} is the joined per-shot blocks (see below).
TOP_TEMPLATE = """\
PREMISE:
{premise}

ORGANIZING PRINCIPLE: {organizing_principle}
WHY THIS PRINCIPLE: {principle_rationale}

SHOTS (3 beats, in order):
{shot_blocks}
ON-SCREEN TEXT: {onscreen_text}
CAPTION: {caption}
"""

# One block per shot. {index} is the 1-based beat number; {end_keyframe_line} is
# "" for an idle beat or a filled END_KEYFRAME_LINE for an event beat.
SHOT_BLOCK_TEMPLATE = """\
--- SHOT {index} ({beat_position}) ---
Start keyframe: {start_keyframe}
{end_keyframe_line}Transition: {transition}
Mood anchor: {mood_anchor}
"""

# Only emitted when shot.end_keyframe is not None (event beats). Your None-guard
# decides whether this line appears.
END_KEYFRAME_LINE = "End keyframe: {end_keyframe}\n"


def render_for_judge(premise: str, package: ContentPackage) -> str:

    blocks = []
    for i, shot in enumerate(package.shots, 1):
        end_keyframe_line = END_KEYFRAME_LINE.format(end_keyframe=shot.end_keyframe) if shot.end_keyframe else ""
        block = SHOT_BLOCK_TEMPLATE.format(
            index=i,
            beat_position=shot.beat_position,
            start_keyframe=shot.start_keyframe,
            end_keyframe_line=end_keyframe_line,
            transition=shot.transition,
            mood_anchor=shot.mood_anchor,
        )
        blocks.append(block)
    
    shot_blocks = " ".join(blocks)

    return TOP_TEMPLATE.format(premise=premise, 
                        organizing_principle=package.organizing_principle,
                        principle_rationale=package.principle_rationale,
                        shot_blocks=shot_blocks,
                        onscreen_text=package.onscreen_text,
                        caption=package.caption,
                        )

   