"""
Render a ContentPackage into the flat text the writer-judge reads (v1 eval).

PURE: premise + package in, string out. No LLM, no I/O — so it is unit-testable
with plain assertions. The WriterJudge (Task 7) takes this string, wraps it with
the anchored rubric + system prompt, and makes the Opus call. The seam is
deliberate: assembling text is cheap/testable here; the paid LLM call lives there.

The format below foregrounds premise + device + mood_anchor at the top (they
condition the premise_fidelity and device_execution dimensions) and emits one
labeled block per chained segment so the take's structure stays visible: segment 1
carries the only opening keyframe; segments 2-3 are marked as inheriting the prior
clip's final frame, so the judge can see the chain rather than three loose shots.
"""

from src.schemas.generation import ContentPackage


# Top-level brief. {segment_blocks} is the joined per-shot blocks (see below).
TOP_TEMPLATE = """\
PREMISE:
{premise}

DEVICE: {device}
WHY THIS DEVICE: {device_rationale}

MOOD ANCHOR:
{mood_anchor}

SEGMENTS:
{segment_blocks}
ON-SCREEN TEXT: {onscreen_text}
CAPTION: {caption}
"""

# Segment 1's block — the ONLY block with a Start keyframe line (segment 1 carries
# the single generated opening still). {end_keyframe_line} is "" when the segment
# has no end_keyframe, or a filled END_KEYFRAME_LINE when it does.
FIRST_SEGMENT_TEMPLATE = """\
--- SEGMENT 1 (opening — carries the hook) ---
Start keyframe: {start_keyframe}
Motion: {motion}
{end_keyframe_line}"""

# Segments 2-3's block — NO keyframe line; the header marks the inherited frame.
# {index} is the 1-based segment number; {prev} is index - 1 (the segment whose
# final frame this one starts on).
LATER_SEGMENT_TEMPLATE = """\
--- SEGMENT {index} (starts on segment {prev}'s final frame) ---
Motion: {motion}
{end_keyframe_line}"""

# Only emitted when shot.end_keyframe is not None.
END_KEYFRAME_LINE = "End keyframe: {end_keyframe}\n"


def render_for_judge(premise: str, package: ContentPackage) -> str:
    """
    Flatten a premise + ContentPackage into the judge-readable brief string.

    Pure (no LLM): one labeled block per shot, end_keyframe line only on event
    beats, joined into the foregrounded top template.
    """
    blocks = []
    opener, *inheritors = package.shots
    end_keyframe_line = END_KEYFRAME_LINE.format(end_keyframe=opener.end_keyframe) if opener.end_keyframe is not None else ""

    blocks.append(FIRST_SEGMENT_TEMPLATE.format(
        start_keyframe=opener.start_keyframe,
        motion=opener.motion,
        end_keyframe_line=end_keyframe_line,
    ))

    for i, inheritor in enumerate(inheritors, start=2):
        block = LATER_SEGMENT_TEMPLATE.format(
            index=i,
            prev=i-1,
            motion=inheritor.motion,
            end_keyframe_line=END_KEYFRAME_LINE.format(end_keyframe=inheritor.end_keyframe) if inheritor.end_keyframe is not None else "",
        )
        blocks.append(block)
    
    segment_blocks = "\n\n".join(blocks)

    return TOP_TEMPLATE.format(premise=premise, 
                            device=package.device,
                            device_rationale=package.device_rationale,
                            mood_anchor=package.mood_anchor,
                            segment_blocks=segment_blocks,
                            onscreen_text=package.onscreen_text,
                            caption=package.caption
                            )

   