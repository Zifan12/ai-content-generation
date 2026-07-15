"""Render adapter: turn a MultiShotPackage into its composed scene RenderJob(s).

This is where prompts become FINAL — the composition seam: anchors_block,
style_anchor, ref bindings, and the constraint tail are assembled HERE, in
code, so identity text is byte-identical on every take and no LLM is ever
trusted to repeat itself verbatim.

TWO LANES, selected by ``scene_lane.mode`` in the yaml (2026-07-14 grill Q1);
``render_jobs`` dispatches and callers stay lane-agnostic:

- ``single_gen`` (DEFAULT, spec 2026-07-06 A3, live-validated 2026-07-07): one
  package -> ONE ``multi_shot`` job on rules.scene_model(), shots chained as
  prose with internal cuts.
- ``per_scene_splice`` (Way 2): one ``scene_shot`` job PER SHOT, each rendered
  as its own standalone generation and hard-cut concatenated at assembly.
  Built by slicing the package per shot and reusing ``_scene_job`` — the
  composition below is common to both lanes (see ``_shot_jobs``).

The scene prompt is composed deterministically:

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

The legacy still-first lane (per-group still + i2v jobs, router-computed
consistency groups) was deleted 2026-07-07 after the live validation render
(plan Task 10, D4 step two) — see git history before commit f7b42bc.
"""

from pathlib import Path

from src.generation.render_adapters.rules import RenderRules
from src.generation.render_adapters.schemas import RenderJob
from src.schemas.generation import MultiShotPackage


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


def _setting_block(package: MultiShotPackage, start_position: int) -> str:
    """Compose the location setting block, or '' when the package is ungrounded.

    The world_anchor text (concrete setting nouns, cached per location) is
    appended verbatim, then a binding sentence names the location refs by their
    upload position. Location refs upload AFTER the character refs, so
    start_position is len(character_refs) + 1. Binding is TEXTUAL on the
    Higgsfield CLI, exactly as for character identity (methodology/19 §1) — the
    model never infers the setting from upload position alone.

    Returns '' when the package carries neither a world_anchor nor a location
    ref, so an ungrounded package composes byte-identically to before this
    feature (backward-compat).

    Args:
        package: The package whose world_anchor / location_reference_paths drive
            the block.
        start_position: The 1-based "(imageN)" slot of the FIRST location ref
            (i.e. one past the last character ref).

    Returns:
        The setting block string, or '' if there is nothing to ground.
    """
    if not package.world_anchor and not package.location_reference_paths:
        return ""
    count = len(package.location_reference_paths)
    slots = ", ".join(f"image{start_position + i}" for i in range(count))
    binding = f" The setting is shown in {slots}." if count else ""
    return f"{package.world_anchor}{binding}".strip()


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
        # 24fps header: Dan-Kieft L52/L592 anti-stutter lever, promoted from
        # sequence_craft_candidates 2026-07-13 — survives zh translation
        # (numerals + Latin tags stay untranslated per the translation stage).
        "24fps. "
        "Exactly matching the art style of the reference images. "
        f"{package.style_anchor}"
    )
    identity = _identity_block(package, ordered)
    setting = _setting_block(package, start_position=len(ordered) + 1)
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
    # Setting block sits in the identity zone (after identity, before the action
    # body) when the package is grounded; ungrounded packages skip it entirely.
    blocks = [preamble, identity, *([setting] if setting else []), body, tail]
    prompt = "\n\n".join(blocks)

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
    override it per-run (--duration flag).
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

    # Character refs first (positional identity binding), then location refs
    # (positional setting binding) — this ordered list IS the CLI upload order
    # and must match the "(imageN)" slots the scene prompt composes.
    ordered = _ordered_refs_by_character(package)
    all_refs = [ref for _name, ref in ordered] + list(package.location_reference_paths)
    if len(all_refs) > limits["max_image_references"]:
        raise ValueError(
            f"{len(all_refs)} image refs (characters + location) — over the "
            f"{limits['max_image_references']} cap (limits.max_image_references)"
        )

    defaults = rules.data["scene_lane"]["defaults"]
    return RenderJob(
        model_cli_id=model_id,
        kind="multi_shot",
        prompt=_scene_prompt(package, rules),
        aspect_ratio=str(defaults["aspect_ratio"]),
        shot_index=0,
        duration=min(int(defaults["duration_seconds"]), int(limits["max_duration_seconds"])),
        reference_images=all_refs,
        covers_shots=list(range(len(package.shots))),
    )


def _shot_jobs(package: MultiShotPackage, rules: RenderRules) -> list[RenderJob]:
    """Build one ``scene_shot`` job per shot (per-scene splice lane, Way 2).

    Where ``_scene_job`` composes ONE generation covering every shot, this
    composes N independent generations — one per shot — which the executor
    renders separately and ``assembly.assemble()`` concatenates. Each shot is
    built by slicing the package down to just that shot and handing the slice
    to ``_scene_job`` itself, so every guard and every composition rule (cast
    cap, ref cap, prompt ceiling, location setting block, positional bindings)
    is inherited rather than re-implemented — the splice lane cannot drift from
    the single_gen lane's composition, because it IS that composition.

    Two things the slice must get right, both load-bearing:

    - ``reference_image_paths`` is sliced alongside ``shots``. Slicing only
      ``shots`` leaves the whole package's refs against a one-shot cast, and
      ``_ordered_refs_by_character`` then rejects every other character's refs
      as unattributable. This is also what implements grill Q3 — a shot's
      generation uploads ONLY its own characters' refs.
    - ``location_reference_paths`` is NOT sliced: a location is not a cast
      member (it bypasses the cast guard and binds its own "(imageN)" setting
      slot), and every shot happens in the same room. Dropping it would render
      an ungrounded room on every clip — the confound that invalidated the
      pitch-47 test.

    Per-shot slot numbering is a deliberate consequence: a character who is
    "image2" in a two-hander is "image1" in their solo shot, because each shot
    is an independent upload. Bindings are composed per shot, so they agree.

    Duration comes from ``scene_lane.splice_defaults`` (grill Q2), never the
    package's ``ShotSpec.duration_seconds`` — that field is a narration/pacing
    budget that never reaches the CLI (see ``schemas/generation.py``).

    Raises:
        ValueError: the same guards ``_scene_job`` raises, prefixed with the
            offending shot index; or an unattributable ref (checked against the
            WHOLE package's cast up front — see below).
    """
    # Validate refs against the FULL cast BEFORE slicing. The per-shot slice
    # silently drops refs belonging to other shots' characters, which is the
    # point (Q3) — but it would equally silently drop a ref that belongs to NO
    # cast member (a typo'd path, a flat legacy layout). This call exists for
    # that crash-loud guard alone; its return value is deliberately unused.
    _ordered_refs_by_character(package)

    limits = rules.model(rules.scene_model())["limits"]
    duration = int(rules.data["scene_lane"]["splice_defaults"]["duration_seconds"])

    jobs: list[RenderJob] = []
    for i, shot in enumerate(package.shots):
        slugs = {_slug(name) for name in shot.characters_in_frame}
        # model_copy does NOT re-validate (pydantic v2) — deliberate here: a
        # one-shot slice violates MultiShotPackage's own min_length=3 and its
        # 10-25s total-duration validator. The slice is a transient carrier for
        # _scene_job, never returned or persisted; constructing it through
        # MultiShotPackage(...) would reject it.
        one_shot = package.model_copy(
            update={
                "shots": [shot],
                "reference_image_paths": [
                    ref
                    for ref in package.reference_image_paths
                    if Path(ref).parent.name in slugs
                ],
            }
        )
        try:
            job = _scene_job(one_shot, rules)
        except ValueError as err:
            raise ValueError(f"shot {i}: {err}") from err

        jobs.append(
            job.model_copy(
                update={
                    "kind": "scene_shot",
                    "duration": min(duration, int(limits["max_duration_seconds"])),
                    "shot_index": i,
                    "covers_shots": [i],
                }
            )
        )
    return jobs


def render_jobs(package: MultiShotPackage, rules: RenderRules) -> list[RenderJob]:
    """Translate a MultiShotPackage into its composed render job(s).

    Dispatches on ``scene_lane.mode`` (2026-07-14 grill Q1), so a caller never
    needs to know which lane it got — only that it got a list of jobs to render
    in order:

    - ``single_gen`` (default, spec 2026-07-06 A3/D3; live-validated
      2026-07-07): ONE composed ``multi_shot`` job covering every shot, in a
      one-element list.
    - ``per_scene_splice`` (Way 2): one ``scene_shot`` job per shot, rendered
      independently and concatenated at assembly (see ``_shot_jobs``).

    The two lanes are config-selectable alternatives, NOT a migration —
    single_gen stays the default and the fallback.

    Raises:
        ValueError: unattributable ref, ungrounded cast member, cast over the
            yaml character cap (whole-package for single_gen, per-shot for
            per_scene_splice), refs over the yaml image cap, or a composed
            prompt over the yaml char ceiling.
    """
    if rules.data["scene_lane"].get("mode", "single_gen") == "per_scene_splice":
        return _shot_jobs(package, rules)
    return [_scene_job(package, rules)]
