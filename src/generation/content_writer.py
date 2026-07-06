"""
Content writer (P3, v3 multi-shot): turns a StoryPitch into a MultiShotPackage.

Two structured-output LLM calls with deterministic code between (spec 2026-07-04
§2.2 — the two-call design keeps routing assertable and failures addressable):

  call 1 (PLAN):    pitch beats -> ShotPlanDraft (per-beat still prompts,
                    model-agnostic motion intents, motion tags, narration polish,
                    package-level style/anchor/caption fields)
  code (ROUTE):     router.route_shots stamps each shot's model from the yaml
                    routing table; router.consistency_groups computes which
                    contiguous shots render as ONE Kling multi-shot generation
  call 2 (DIALECT): per distinct routed model, motion intents -> model-native
                    motion prompts in that model's dialect block from
                    config/render_rules.yaml

The writer TRUSTS CODE OVER THE LLM at every seam: beat_role / characters_in_frame
are copied from the pitch (never the draft's echo), silence is preserved (a beat
with narration_line=None stays silent even if the draft invents a line), the model
id comes from the router, hook_text comes from the gate-judged pitch.hook_line, and
provenance (pitch_id / reference_image_paths / consistency_groups) is code-set.

anchors_block and style_anchor are package-level fields composed into prompts by
the ADAPTER (D10) — call 1 is explicitly instructed to keep them OUT of per-shot
prompts, and the adapter appends them deterministically so the identity sentence is
byte-identical across every still.

RAG grounding (hits/_hydrate_hits) was removed with the found-footage register
(D15) — the winners corpus grounded a retired lane and had no live callers.
"""

import json
import logging

from pydantic import BaseModel, ConfigDict

from src.generation.render_adapters.router import (
    RoutingDecision,
    consistency_groups,
    route_shots,
)
from src.generation.render_adapters.rules import RenderRules
from src.monitor.schemas import StoryPitch
from src.schemas.generation import (
    MultiShotPackage,
    ShotPlanDraft,
    ShotSpec,
)

logger = logging.getLogger(__name__)

# Explicit per-caller override of the shared parse() default (1024) — big packages
# truncate silently at the default (bitten 3x, memory feedback_shared_max_tokens).
# 8192 -> 16384 (2026-07-05): deepseek-v4-pro's ShotPlanDraft for a 5-beat pitch
# overflowed 8192 on one roll of the pitch-29 render (nondeterministic verbosity;
# two prior rolls of the SAME pitch fit under it). 4th max_tokens bite project-wide.
WRITER_MAX_TOKENS = 16384

PLAN_SYSTEM_PROMPT = """\
<role>
You are the story-to-screen developer for a channel that renders the scene a
fandom is currently begging to see. The finished video must read as a DELETED
SCENE OR OFFICIAL CLIP from the source work itself — matched to that work's own
visual register — not as "an AI video of the character in our world."
</role>

<inputs>
You receive:
1. A STORY PITCH (JSON) — a judged, approved story: logline, mode (wish/satire),
   characters, desired_moment, and 3-6 ordered beats. Each beat has a role
   (hook/establish/build/turn/escalate/reveal/payoff/tag), a visual_line (what the
   camera sees), an optional narration_line, a shot_size, and characters_in_frame.
   Develop THIS story. Never substitute your own.
2. A STILL DIALECT block — the image-model prompting rules for opening stills
   (directive-stack order, spatial mapping, camera kit, light naming, composition
   traps). Obey it in every still_prompt.
3. A MOTION CRAFT block — universal motion-prompt rules (one move + one action,
   countable beats, emotion as visible physical tells, banned dead words).
</inputs>

<task>
Produce a ShotPlanDraft: exactly ONE shot per pitch beat, in the same order, plus
the package-level creative fields. This plan is later converted per-model and
rendered as 3-6 clips assembled into one 12-25 second vertical video.
</task>

<per_shot_rules>
- still_prompt: the shot's opening frame as an IMAGE prompt in the STILL DIALECT.
  Subject-first, literal spatial layout, honor the beat's shot_size, name the
  physical light source. Describe the CHARACTER ONLY BY ROLE OR ACTION POSITION
  (e.g. "the swordswoman mid-lunge") — do NOT write identity descriptions (name,
  hair, outfit) and do NOT write art-style words. Identity and style are appended
  by the system from the anchors_block and style_anchor you provide once; a second
  in-prompt description fights the appended one and causes drift.
- motion_intent: the shot's movement in plain craft language, model-agnostic:
  ONE camera move + ONE subject action, expressed as countable beats with timing,
  plus the concrete diegetic sounds of the moment (name actual sounds, never
  "ambient sounds"). No music. No style or palette words. Between adjacent shots,
  author a MATCH CUT: end this shot on a shape or motion the next shot opens on.
- motion_tag: classify what the shot NEEDS rendered — fluid/water physics
  (fluid_motion), physically impossible held states (impossible_physics),
  melt/morph/grow (transformation), epic scale spectacle (spectacle), or ordinary
  character action where cross-shot identity matters most (character_consistency —
  the default for character beats).
- duration_seconds: integer 4-8 per shot, total 12-25. 4 is a HARD FLOOR — never
  emit 3 or less, even for the hook. Give the payoff beat air; keep the hook tight
  at exactly 4. Prefer keeping contiguous same-cast character beats within about
  10 seconds combined (they render as one consistency group).
- narration_line: polish the beat's narration into spoken-word text at a budget of
  at most 2.2 words per second of the shot. A beat whose narration_line is null is
  a deliberate silent beat — return null for it, never invent narration.
</per_shot_rules>

<package_rules>
- style_anchor: ONE line naming the source work's visual register concretely (for
  an anime: its animation style, line quality, palette family, broadcast grade;
  for a game/live-action register: its cinematography). This is appended to every
  still, so it must be true for every shot.
- anchors_block: one identity sentence per character who appears on screen — name,
  hair, outfit category + primary color, and one recognition trait, matched to the
  supplied reference art era. This is prepended to every still verbatim.
- caption: native creator voice for the fandom, may seed a comment-driving question.
- hashtags: a small mix — one or two broad tags plus a couple of fandom tags.
- music_brief: one line describing the score that fits the mode and source (or
  null for no music).
- hook_text: ignore — the system takes the hook from the approved pitch.
</package_rules>

<constraints>
- Exactly one shot per beat, same order. Emotion must be a visible physical tell.
- Cut empty adjectives (epic, amazing, stunning); write the concrete subject,
  light, or action they stood for.
- The payoff must happen ON SCREEN in its shot — a pretty frame where nothing
  resolves is the failure mode.
</constraints>
"""

DIALECT_SYSTEM_PROMPT = """\
<role>
You are a prompt translator for ONE specific AI video model. You convert
model-agnostic motion intents into that model's native prompt grammar — nothing
more. You add no new creative content.
</role>

<inputs>
1. A MODEL DIALECT block (JSON) — the target model's prompting grammar, structure
   rules, and (if present) multi_shot_grammar and multi_shot_limits.
2. A SHOT LIST — for each shot: its index, beat role, duration in seconds, its
   consistency group (shots in the same group render as ONE multi-shot generation),
   and its motion_intent.
</inputs>

<task>
Return one motion prompt per shot, in the same order, in the model's dialect.
</task>

<rules>
- These are image-to-video prompts: the input still already carries the look.
  Describe ONLY camera movement, subject action, timing, and audio. Never
  re-describe the still's contents, palette, or style.
- Preserve each intent's single camera move + single subject action and its
  countable beats. Do not add moves, subjects, or style words.
- Every prompt MUST end with a concrete diegetic "Audio:" line naming actual
  sounds (never "ambient sounds"). No music.
- If the dialect has multi_shot_grammar and a shot belongs to a multi-member
  group: write that shot's line in the group grammar's member form — starting
  with an explicit angle/framing statement (non-first members open with an
  angle-change verb like "Change angle to" / "Switch to"), then the action, then
  the Audio: line — but do NOT write the "Shot N (Xs-Ys):" label itself; the
  system prepends labels and computed timestamps. Respect multi_shot_limits.
  Single-member shots use the model's normal i2v form.
- Respect any per-shot character limits the dialect declares.
</rules>
"""


class DialectConversion(BaseModel):
    """Call 2's structured output: model-native motion prompts, one per input shot,
    in the same order. Count is validated against the request — a mismatch fails
    loud rather than mis-assigning prompts to shots."""

    model_config = ConfigDict(extra="forbid")

    motion_prompts: list[str]


def _build_plan_envelope(pitch: StoryPitch, rules: RenderRules) -> str:
    """Assemble call 1's user prompt: pitch JSON + still dialect + motion craft.

    The PLAN_SYSTEM_PROMPT promises these three labeled inputs; dialect blocks are
    serialized with json.dumps so their full rule text lands verbatim (reference
    material, not JSON to echo).
    """
    return "\n\n".join(
        [
            f"Story pitch:\n{pitch.model_dump_json(indent=2)}",
            f"Still dialect:\n{json.dumps(rules.still_dialect(), indent=2)}",
            f"Motion craft:\n{json.dumps(rules.data['motion_craft'], indent=2)}",
        ]
    )


def _build_dialect_envelope(
    model_cli_id: str,
    shot_indices: list[int],
    plan: ShotPlanDraft,
    groups: list[list[int]],
    rules: RenderRules,
) -> str:
    """Assemble call 2's user prompt for one model: dialect block + its shot list.

    Each shot line carries index, beat role, duration, its consistency-group
    membership (so multi-member Kling shots are written in the group grammar with
    cumulative timestamps), and the motion_intent to convert. Groups are described
    by their member indices; single-member groups mean normal i2v form.
    """
    group_of = {index: group for group in groups for index in group}
    lines = [f"Model dialect ({model_cli_id}):"]
    lines.append(json.dumps(rules.model(model_cli_id)["dialect"], indent=2))
    lines.append("")
    lines.append("Shots to convert (return prompts in this order):")
    for index in shot_indices:
        shot = plan.shots[index]
        group = group_of.get(index, [index])
        membership = (
            f"group {group} (multi-shot generation, {len(group)} shots)"
            if len(group) > 1
            else "single-shot generation"
        )
        lines.append(
            f"- shot_index={index} beat_role={shot.beat_role.value} "
            f"duration={shot.duration_seconds}s {membership}\n"
            f"  motion_intent: {shot.motion_intent}"
        )
    return "\n".join(lines)


class ContentWriter:
    """Turns a judged StoryPitch into a validated MultiShotPackage.

    Two structured-output calls on the injected llm seat, with the deterministic
    router between them (module docstring). Construction takes the llm only;
    rules and grounding references arrive per-write call.
    """

    def __init__(self, llm):
        self.llm = llm

    def write(
        self,
        pitch: StoryPitch,
        *,
        rules: RenderRules,
        reference_image_paths: list[str],
        pitch_id: int | None = None,
    ) -> MultiShotPackage:
        """Generate one MultiShotPackage from an approved StoryPitch.

        Runs the plan call, validates one-shot-per-beat cardinality, routes and
        groups the shots in code, runs one dialect call per distinct routed model,
        then assembles the package with code-set provenance.

        Args:
            pitch: The approved StoryPitch (loaded from AnglePitchRecord.story_json).
            rules: Loaded render_rules.yaml view (dialects + routing + caps).
            reference_image_paths: Key-art files that will ground every still —
                stamped into the package for the adapter/executor (grounding is
                mandatory, DECISIONS_LOCKED L3; emptiness is NOT validated here —
                the render layer owns that gate).
            pitch_id: AnglePitchRecord id for provenance, when written from the DB.

        Returns:
            A validated MultiShotPackage with len(pitch.beats) shots.

        Raises:
            ValueError: if the plan's shot count differs from the pitch's beat
                count, or a dialect call returns a prompt count that differs from
                its request (fail loud over mis-assignment).
        """
        plan = self.llm.parse(
            _build_plan_envelope(pitch, rules),
            ShotPlanDraft,
            system=PLAN_SYSTEM_PROMPT,
            max_tokens=WRITER_MAX_TOKENS,
        )
        if len(plan.shots) != len(pitch.beats):
            raise ValueError(
                f"plan produced {len(plan.shots)} shots for {len(pitch.beats)} "
                "beats — one shot per beat is the contract"
            )

        decisions: list[RoutingDecision] = route_shots(plan.shots, rules)
        groups = consistency_groups(plan.shots, decisions, rules)
        for decision in decisions:
            logger.info("routing: %s", decision.reason)

        # Batch call 2 per distinct routed model, preserving shot order per model.
        indices_by_model: dict[str, list[int]] = {}
        for decision in decisions:
            indices_by_model.setdefault(decision.model_cli_id, []).append(
                decision.shot_index
            )

        motion_prompts: dict[int, str] = {}
        for model_cli_id, shot_indices in indices_by_model.items():
            conversion = self.llm.parse(
                _build_dialect_envelope(model_cli_id, shot_indices, plan, groups, rules),
                DialectConversion,
                system=DIALECT_SYSTEM_PROMPT,
                max_tokens=WRITER_MAX_TOKENS,
            )
            if len(conversion.motion_prompts) != len(shot_indices):
                raise ValueError(
                    f"dialect call for {model_cli_id} returned "
                    f"{len(conversion.motion_prompts)} prompts for "
                    f"{len(shot_indices)} shots"
                )
            for index, prompt in zip(shot_indices, conversion.motion_prompts):
                motion_prompts[index] = prompt

        # Assemble ShotSpecs — code copies the pitch's own beat facts (role, cast,
        # silence) rather than trusting the draft's echo of them.
        shots = []
        for index, (beat, draft, decision) in enumerate(
            zip(pitch.beats, plan.shots, decisions)
        ):
            narration = (
                draft.narration_line if beat.narration_line is not None else None
            )
            shots.append(
                ShotSpec(
                    beat_role=beat.role,
                    motion_tag=draft.motion_tag,
                    still_prompt=draft.still_prompt,
                    motion_prompt=motion_prompts[index],
                    duration_seconds=draft.duration_seconds,
                    narration_line=narration,
                    characters_in_frame=list(beat.characters_in_frame),
                    model_cli_id=decision.model_cli_id,
                )
            )

        return MultiShotPackage(
            shots=shots,
            style_anchor=plan.style_anchor,
            anchors_block=plan.anchors_block,
            hook_text=pitch.hook_line,  # gate-judged text wins over the draft's
            caption=plan.caption,
            hashtags=plan.hashtags,
            music_brief=plan.music_brief,
            rationale=plan.rationale,
            pitch_id=pitch_id,
            reference_image_paths=list(reference_image_paths),
            consistency_groups=groups,
        )
