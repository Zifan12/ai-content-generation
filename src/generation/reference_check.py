"""Pre-render reference check: does this pitch have the images it needs?

Reads the SHARED reference library (refs/<char_slug>/ and
refs/_location/<slug>/) and reports, per required reference, whether it is
present — WITHOUT rendering, spending, or fetching anything (detect + stop,
spec 2026-07-11 decision #1). The smoke/render entrypoint halts on a
not-ready manifest before the paid writer call.

Required references are derived from the pitch itself: every in-frame
character marked needs_reference, plus the location named by location_slug.
Folder resolution reuses the adapter's _slug so it can never drift from what
the render actually binds.
"""

from dataclasses import dataclass, field
from pathlib import Path

from src.generation.render_adapters.adapter import _slug
from src.monitor.schemas import StoryPitch

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
_REFS_ROOT = Path("refs")
_LOCATION_ROOT = _REFS_ROOT / "_location"

# Vendor guidance is that a character reference is a headshot + a full-body shot,
# and NOTHING else: [cited] ai_video_resources/lanshu-awesome-ai-video-kit/
# methodology/08-避坑12问.md:21 — 人物参考使用大头照 + 全身照即可，不建议使用人物多视图。
# 多视图素材包含同一人物的不同角度，模型易将其识别为多个不同主体，反而加剧 ID 漂移问题。
# ("multi-view material contains the same person at different angles, so the model
# reads them as multiple different subjects, which WORSENS ID drift.")
#
# We violated this until 2026-07-15 by sending 4 refs/character including a
# FRONT/SIDE/BACK/THREE-QUARTER turnaround page — a directly documented mechanism
# for the pose-reset symptom we were chasing. It confounded every render to that
# date. This is an ADVISORY, not a gate: `present` still means "has any image at
# all", because the vendor claim is single-source and unmeasured on the Higgsfield
# CLI. It prints in the manifest, which the operator reads before any spend — a
# warning where the decision is actually made beats a rule nobody remembers.
_VENDOR_REFS_PER_CHARACTER = 2


@dataclass
class RequiredRef:
    """One reference the pitch needs, and whether the library has it.

    has_description is location-only (None for characters). detail is a short
    human-facing status used by render_manifest.
    """

    kind: str  # "character" | "location"
    label: str
    slug: str
    folder: str
    images: list[str]
    present: bool
    has_description: bool | None
    detail: str


@dataclass
class ReferenceManifest:
    """The full pre-render picture: every required ref + the derived paths.

    character_reference_paths / location_reference_paths are the ordered lists
    handed to ContentWriter.write when ready is True. ready is False if ANY
    required item is not present.
    """

    items: list[RequiredRef]
    ready: bool
    character_reference_paths: list[str] = field(default_factory=list)
    location_reference_paths: list[str] = field(default_factory=list)


def _images_in(folder: Path) -> list[str]:
    """Sorted image paths in a folder (empty list if the folder is absent)."""
    if not folder.is_dir():
        return []
    return sorted(
        str(p) for p in folder.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES
    )


def _in_frame_cast_needing_refs(pitch: StoryPitch) -> list[str]:
    """First-appearance-ordered character names that are in-frame AND need refs.

    A character requires grounding only if it actually appears in some beat's
    characters_in_frame AND its CharacterRef.needs_reference is True — the same
    two facts the harvester and adapter honor.
    """
    needs = {c.name for c in pitch.characters if c.needs_reference}
    ordered: list[str] = []
    for beat in pitch.beats:
        for name in beat.characters_in_frame:
            if name in needs and name not in ordered:
                ordered.append(name)
    return ordered


def check_references(pitch: StoryPitch, location_slug: str | None) -> ReferenceManifest:
    """Build the reference manifest for a pitch against the shared library.

    Args:
        pitch: The StoryPitch whose cast + beats drive the required characters.
        location_slug: The pitch's location tag, or None for no location.

    Returns:
        A ReferenceManifest: one RequiredRef per required reference, the ready
        flag (True iff every item is present), and the ordered character/
        location reference-path lists to hand the writer when ready.
    """
    items: list[RequiredRef] = []

    for name in _in_frame_cast_needing_refs(pitch):
        slug = _slug(name)
        folder = _REFS_ROOT / slug
        images = _images_in(folder)
        present = bool(images)
        # A voice profile is OPTIONAL grounding: its absence never flips present/
        # ready (a character with no profile just stays silent, spec Q3-B) — it only
        # annotates the operator-facing detail so onboarding sees what's missing.
        has_profile = (folder / "voice_profile.md").is_file()
        base_detail = f"{len(images)} images" if present else "MISSING — drop key-art here"
        voice_note = "" if has_profile else "  (no voice profile — silent; run gen_voice_profile)"
        # Every image in the folder is sent to the render, so an extra page here is
        # not free — it is another subject the model may read as a different person.
        multiview_note = (
            f"  !! {len(images)} refs — vendor says headshot + full-body ONLY "
            "(multi-view reads as MULTIPLE people and worsens ID drift); "
            "archive the extras before trusting this render"
            if len(images) > _VENDOR_REFS_PER_CHARACTER
            else ""
        )
        items.append(
            RequiredRef(
                kind="character",
                label=name,
                slug=slug,
                folder=str(folder),
                images=images,
                present=present,
                has_description=None,
                detail=base_detail + voice_note + multiview_note,
            )
        )

    if location_slug:
        folder = _LOCATION_ROOT / location_slug
        images = _images_in(folder)
        has_description = (folder / "world_anchor.txt").is_file()
        present = bool(images) and has_description
        if not images:
            detail = "MISSING — drop a room screencap here"
        elif not has_description:
            detail = (
                "picture ok, NO description — run: "
                f"gen_location_anchor.py --slug {location_slug}"
            )
        else:
            detail = f"{len(images)} image(s) + description"
        items.append(
            RequiredRef(
                kind="location",
                label=location_slug,
                slug=location_slug,
                folder=str(folder),
                images=images,
                present=present,
                has_description=has_description,
                detail=detail,
            )
        )

    char_paths = [p for it in items if it.kind == "character" for p in it.images]
    loc_paths = [p for it in items if it.kind == "location" for p in it.images]
    return ReferenceManifest(
        items=items,
        ready=all(it.present for it in items),
        character_reference_paths=char_paths,
        location_reference_paths=loc_paths,
    )


def render_manifest(manifest: ReferenceManifest) -> str:
    """Format the manifest as the operator-facing block printed before spend."""
    lines = ["reference check"]
    for it in manifest.items:
        mark = "OK " if it.present else "!! "
        lines.append(
            f"  {mark}{it.kind:9} {it.label} -> {it.folder}  {it.detail}"
        )
    lines.append(
        "  READY"
        if manifest.ready
        else "  NOT READY — provide the above, then re-run."
    )
    return "\n".join(lines)
