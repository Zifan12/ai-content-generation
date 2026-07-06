"""Render adapter v3: turn a MultiShotPackage into grouped, composed RenderJobs.

This is where prompts become FINAL — the composition seam (spec 2026-07-04 §3.3,
D10): anchors_block, style_anchor, and the yaml's global constraint buckets are
appended to prompts HERE, in code, so the identity sentence is byte-identical
across every still and no LLM is ever trusted to repeat itself verbatim. This
call site is also what puts ``rules.global_constraints()`` into the live render
path (the second half of audit issue 10; ``rules.route()`` went live in router.py).

Per consistency group (router-computed, package.consistency_groups):

  multi-member group  ->  ONE still job (grounded on the package's key-art refs,
                          prompt = anchors + FIRST member's still_prompt + style +
                          still constraints) + ONE ``multi_shot`` job whose prompt
                          is the members' motion prompts joined under computed
                          "Shot k (a-bs):" labels (code arithmetic — cumulative
                          in-group timestamps; the LLM never does the math).

  singleton group     ->  ONE still job + ONE ``motion`` job in the model's normal
                          i2v form.

Stills carry reference_images (grounding is mandatory, DECISIONS_LOCKED L3);
executors seed each video job with its group's rendered still at submit time
(image wiring is an executor concern — jobs are declarations, not calls).
"""

from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob
from src.schemas.generation import MultiShotPackage, ShotSpec

# The opening still is an IMAGE render; nano-banana Pro is the locked reference-
# consuming identity model (MODEL_ROUTING; June-14 taste test 4/4).
STILL_MODEL = "nano_banana_2"

ASPECT_RATIO = "9:16"


def _still_prompt(shot: ShotSpec, package: MultiShotPackage, rules: RenderRules) -> str:
    """Compose a shot's final still prompt: anchors + shot + style + constraints.

    Order is the contract (spec §7 Stage-3 criterion 2): identity first (heaviest
    weight under the still dialect's directive-stack rule), then the shot's own
    framing/content, then the style anchor, then the yaml's still-kind constraint
    strings with [STYLE] resolved to the style anchor.
    """
    # `or ""`: still_prompt is legacy-defaulted None on scene-lane packages (D4
    # bridge until the Task-10 deletion of this whole still-first path).
    parts = [package.anchors_block, shot.still_prompt or "", package.style_anchor]
    parts.extend(rules.global_constraints("still", style=package.style_anchor))
    return " ".join(parts)


def _motion_prompt(shot: ShotSpec, rules: RenderRules) -> str:
    """Compose a singleton shot's final motion prompt: prompt + motion constraints.

    Motion prompts carry no style text ([STYLE] collapses to empty per the i2v
    rule — the still owns the look), so constraints are fetched with style="".
    """
    parts = [shot.scene_line]
    parts.extend(rules.global_constraints("motion", style=""))
    return " ".join(parts)


def _group_prompt(
    members: list[ShotSpec], rules: RenderRules
) -> str:
    """Compose a multi-shot group's prompt: labeled member lines + constraints.

    Labels and cumulative timestamps are computed here — "Shot k (a-bs):" with k
    1-based within the group (the spike-proven Kling-native grammar; the label
    format is load-bearing, DECISIONS_LOCKED D-consistency). The dialect call
    already wrote each member's line in member form (angle-change verb + action +
    Audio:) WITHOUT the label.
    """
    lines = []
    elapsed = 0
    for position, shot in enumerate(members, start=1):
        start, end = elapsed, elapsed + shot.duration_seconds
        lines.append(f"Shot {position} ({start}-{end}s): {shot.scene_line}")
        elapsed = end
    lines.extend(rules.global_constraints("motion", style=""))
    return "\n".join(lines)


def render_jobs(package: MultiShotPackage, rules: RenderRules) -> list[RenderJob]:
    """Translate a MultiShotPackage into its ordered, composed render jobs.

    Emits per consistency group, in shot order: one grounded ``still`` job, then
    one video job — ``multi_shot`` for multi-member groups (duration = summed
    member durations; router already enforced the model's yaml caps) or
    ``motion`` for singletons (duration capped at the model's max_seconds).

    Every still job carries package.reference_image_paths; every prompt carries
    its kind's global-constraint strings. Group order and job order follow shot
    order, so the executor can zip stills to their video jobs pairwise.

    Args:
        package: The writer's output (consistency_groups already router-computed).
        rules: Loaded render rules — constraint buckets + per-model caps.

    Returns:
        A flat job list: [group0 still, group0 video, group1 still, ...].
    """
    jobs: list[RenderJob] = []
    for group in package.consistency_groups:
        members = [package.shots[i] for i in group]
        first = members[0]

        jobs.append(
            RenderJob(
                model_cli_id=STILL_MODEL,
                kind="still",
                prompt=_still_prompt(first, package, rules),
                aspect_ratio=ASPECT_RATIO,
                shot_index=group[0],
                duration=None,
                reference_images=list(package.reference_image_paths),
            )
        )

        if len(members) > 1:
            jobs.append(
                RenderJob(
                    model_cli_id=first.model_cli_id,
                    kind="multi_shot",
                    prompt=_group_prompt(members, rules),
                    aspect_ratio=ASPECT_RATIO,
                    shot_index=group[0],
                    duration=sum(shot.duration_seconds for shot in members),
                    covers_shots=list(group),
                )
            )
        else:
            jobs.append(
                RenderJob(
                    model_cli_id=first.model_cli_id,
                    kind="motion",
                    prompt=_motion_prompt(first, rules),
                    aspect_ratio=ASPECT_RATIO,
                    shot_index=group[0],
                    duration=min(
                        first.duration_seconds, rules.max_seconds(first.model_cli_id)
                    ),
                )
            )
    return jobs
