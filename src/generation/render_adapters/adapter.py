"""Render adapter: turn a MultiShotPackage into composed RenderJob(s).

This is where prompts become FINAL — the composition seam: anchors_block,
style_anchor, ref bindings, and the constraint tail are assembled HERE, in
code, so identity text is byte-identical on every take and no LLM is ever
trusted to repeat itself verbatim.

SCENE LANE (current, spec 2026-07-06 A3): one package -> ONE ``multi_shot``
job on rules.scene_model(). The scene prompt is composed deterministically:

  style preamble ("exactly matching the art style of the reference images"
  + style_anchor)  ->  identity block (anchors_block verbatim + one binding
  sentence per character naming its positional "(imageN)" refs — binding is
  TEXTUAL; the model never infers identity from upload position alone,
  methodology/19 §1)  ->  shot scene_lines joined with "Then cut to:"  ->
  constraint tail (no-text line + "no music" (D5) + the yaml quality suffix).

Character refs resolve by PATH CONVENTION (locked 2026-07-06): a ref's parent
folder name is the character slug (``refs/<slug>/*.png`` — the layout
scripts/make_char_sheet.py writes). Upload order is deterministic — cast in
first-appearance order across shots, each character's refs sorted by filename
— and any ref that matches no cast member, or any cast member with no refs
(mandatory grounding, DECISIONS_LOCKED L3), CRASHES LOUD.

LEGACY (still-first lane, D4 — unreached in prod, deleted in Task 10): a
package whose consistency_groups is non-empty takes the old per-group
still+i2v path below. The scene-lane writer always leaves groups empty.
"""

from pathlib import Path

from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob
from src.schemas.generation import MultiShotPackage, ShotSpec

# LEGACY (D4): the opening still of the still-first lane; nano-banana Pro was
# the locked reference-consuming identity model (MODEL_ROUTING; June-14 test).
STILL_MODEL = "nano_banana_2"

ASPECT_RATIO = "9:16"


def _slug(name: str) -> str:
    """Character name -> refs-folder slug: lowercase, spaces to underscores.

    Kept deliberately dumb — it must match what scripts/make_char_sheet.py uses
    to name output folders, and both sides normalize the same way.
    """
    return name.strip().lower().replace(" ", "_")


def _ordered_refs_by_character(package: MultiShotPackage) -> list[tuple[str, str]]:
    """Resolve the package's flat ref list into a deterministic (name, path) order.

    Path convention (locked 2026-07-06): a ref belongs to the character whose
    slug equals its parent folder name (``refs/<slug>/front.png`` -> the cast
    member whose _slug() is ``<slug>``). Cast order = first appearance across
    shots; within a character, refs sort by filename. The returned order IS the
    CLI upload order, so index i here becomes "(image{i+1})" in the prompt.

    Crashes loud (ValueError) on:
      - a ref whose parent folder matches no cast member — a silently unbound
        ref would still consume an image slot and dilute identity attention;
      - a cast member with zero refs — grounding is mandatory (DECISIONS_LOCKED
        L3); the fix is generating a sheet via scripts/make_char_sheet.py.
    """
    cast: list[str] = []
    for shot in package.shots:
        for name in shot.characters_in_frame:
            if name not in cast:
                cast.append(name)
    by_slug = {_slug(name): name for name in cast}

    grouped: dict[str, list[str]] = {name: [] for name in cast}
    for ref in package.reference_image_paths:
        folder = Path(ref).parent.name
        owner = by_slug.get(folder)
        if owner is None:
            raise ValueError(
                f"reference {ref!r} has folder slug {folder!r} which matches no "
                f"cast member (cast slugs: {sorted(by_slug)}); refs must live in "
                "refs/<character_slug>/ (path convention, 2026-07-06)"
            )
        grouped[owner].append(ref)

    for name in cast:
        if not grouped[name]:
            raise ValueError(
                f"cast member {name!r} has no reference images — grounding is "
                "mandatory (DECISIONS_LOCKED L3); generate a sheet with "
                "scripts/make_char_sheet.py"
            )

    return [(name, ref) for name in cast for ref in sorted(grouped[name])]


def _identity_block(package: MultiShotPackage, ordered: list[tuple[str, str]]) -> str:
    """Compose the identity block: anchors verbatim + positional ref bindings.

    anchors_block (one identity sentence per character, written once by call 1)
    goes in verbatim; then one binding sentence per character names its refs by
    upload position — "(imageN)" — because binding is textual on the Higgsfield
    CLI (FINDINGS.md; methodology/19 §1), never inferred from order alone.
    """
    positions: dict[str, list[int]] = {}
    for index, (name, _ref) in enumerate(ordered, start=1):
        positions.setdefault(name, []).append(index)
    bindings = [
        f"{name} is the character shown in "
        + ", ".join(f"image{i}" for i in indices)
        + "."
        for name, indices in positions.items()
    ]
    return " ".join([package.anchors_block, *bindings])


def _scene_prompt(package: MultiShotPackage, rules: RenderRules) -> str:
    """Compose the final scene prompt per spec A3 — order is the contract.

    style preamble -> identity block -> "Then cut to:"-joined scene lines ->
    constraint tail. The tail carries the no-text line, the "no music" line
    (D5: SFX stay native, music/narration are added at assembly), and the
    model's own quality suffix from the yaml dialect — exactly once.

    Raises:
        ValueError: if the composed prompt exceeds the model's yaml
            max_prompt_chars (hard Higgsfield ceiling, methodology/15
            L364-366), or via the ref-resolution helpers.
    """
    model_block = rules.model(rules.scene_model())
    ordered = _ordered_refs_by_character(package)

    preamble = (
        "Exactly matching the art style of the reference images. "
        f"{package.style_anchor}"
    )
    identity = _identity_block(package, ordered)
    body = " ".join(
        shot.scene_line if i == 0 else f"Then cut to: {shot.scene_line}"
        for i, shot in enumerate(package.shots)
    )
    quality_suffix = " ".join(model_block["dialect"]["quality_suffix"].split())
    tail = (
        "No on-screen text, no subtitles, no watermark, no logo. "  # yaml always_append no-text rule
        "No music. "  # D5: music + narration are assembly-side
        f"{quality_suffix}"
    )
    prompt = "\n\n".join([preamble, identity, body, tail])

    max_chars = model_block["limits"]["max_prompt_chars"]
    if len(prompt) > max_chars:
        raise ValueError(
            f"scene prompt is {len(prompt)} chars, over the {max_chars} "
            f"ceiling for {rules.scene_model()} (limits.max_prompt_chars)"
        )
    return prompt


def _scene_job(package: MultiShotPackage, rules: RenderRules) -> RenderJob:
    """Build the ONE multi_shot job that renders the whole package (D3).

    Cast size is validated against the model's yaml max_characters_in_scene
    (>3 characters misplace/fuse, methodology/15 L136-139) and ref count
    against max_image_references before composing. Duration comes from
    scene_lane.defaults capped at the measured CLI limit; the executor may
    override it per-run (Task 5 flags).
    """
    model_id = rules.scene_model()
    model_block = rules.model(model_id)
    limits = model_block["limits"]

    cast = {name for shot in package.shots for name in shot.characters_in_frame}
    if len(cast) > limits["max_characters_in_scene"]:
        raise ValueError(
            f"{len(cast)} characters in scene ({sorted(cast)}) — over the "
            f"{limits['max_characters_in_scene']} cap (limits.max_characters_in_scene)"
        )
    if len(package.reference_image_paths) > limits["max_image_references"]:
        raise ValueError(
            f"{len(package.reference_image_paths)} image refs — over the "
            f"{limits['max_image_references']} cap (limits.max_image_references)"
        )

    ordered = _ordered_refs_by_character(package)
    defaults = rules.data["scene_lane"]["defaults"]
    return RenderJob(
        model_cli_id=model_id,
        kind="multi_shot",
        prompt=_scene_prompt(package, rules),
        aspect_ratio=str(defaults["aspect_ratio"]),
        shot_index=0,
        duration=min(int(defaults["duration_seconds"]), int(limits["max_duration_seconds"])),
        reference_images=[ref for _name, ref in ordered],
        covers_shots=list(range(len(package.shots))),
    )


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
    """Translate a MultiShotPackage into its composed render job(s).

    SCENE LANE (the live path): a package with empty consistency_groups — the
    only kind the scene-lane writer produces — yields exactly ONE composed
    ``multi_shot`` job on rules.scene_model() (spec 2026-07-06 A3/D3).

    LEGACY (D4, unreached in prod, deleted in Task 10): a package carrying
    router-computed consistency_groups takes the old still-first path — per
    group, one grounded ``still`` job plus one ``multi_shot``/``motion`` job.

    Args:
        package: The writer's output.
        rules: Loaded render rules — scene lane + dialects + caps.

    Returns:
        Scene lane: ``[the one multi_shot scene job]``.
        Legacy: ``[group0 still, group0 video, group1 still, ...]``.

    Raises:
        ValueError: scene lane only — unattributable ref, ungrounded cast
            member, cast over the yaml character cap, refs over the yaml image
            cap, or a composed prompt over the yaml char ceiling.
    """
    if not package.consistency_groups:
        return [_scene_job(package, rules)]

    # ---- LEGACY still-first path below (D4) ----
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
