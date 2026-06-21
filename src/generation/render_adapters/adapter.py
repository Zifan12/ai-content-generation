from src.generation.render_adapters.builders.base import PromptBuilder
from src.generation.render_adapters.router import classify_motion, pick_model
from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob
from src.schemas.generation import ContentPackage

# The opening still is an IMAGE render, not a video one — it has no entry in the
# yaml routing table (which ranks VIDEO models). nano_banana_2 is the project's
# standard photoreal opening-still model.
STILL_MODEL = "nano_banana_2"


def render_jobs(package: ContentPackage, rules: RenderRules, builders: dict[str, PromptBuilder], available: set[str])  -> list[RenderJob]:

    result = []

    for index, shot in enumerate(package.shots):

        motion = classify_motion(shot, package.device)
        model = pick_model(motion, rules, available)

        if shot.start_keyframe is not None:
            result.append(RenderJob(
                model_cli_id=STILL_MODEL,
                kind="still",
                prompt=builders[model].build_still_prompt(shot, package.mood_anchor),
                aspect_ratio="9:16",
                shot_index=index,
                duration=None,
            ))

        result.append(RenderJob(
            model_cli_id=model,
            kind="motion",
            prompt=builders[model].build_motion_prompt(shot, model),
            aspect_ratio="9:16",
            shot_index=index,
            duration=rules.max_seconds(model)
        ))

        # Keyframe (start->end interpolation) escalation: only when the shot has a
        # target end-state AND routed to impossible physics, which plain i2v can't pin.
        # TODO: lift "impossible_physics" to a rules.needs_keyframe(tag) lookup so the
        # escalation policy lives in the yaml `escalation` block, not hardcoded here.
        if shot.end_keyframe is not None and motion == "impossible_physics":
            result.append(RenderJob(
                model_cli_id=model,
                kind="keyframe",
                prompt=builders[model].build_motion_prompt(shot, model),
                aspect_ratio="9:16",
                shot_index=index,
                duration=rules.max_seconds(model),
                start_image=shot.start_keyframe,
                end_image=shot.end_keyframe,
            ))

    return result
