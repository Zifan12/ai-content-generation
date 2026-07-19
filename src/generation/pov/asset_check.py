"""POV asset gate (ticket 10) — canon-subject reference validation + request sheets.

Slice ② (PRD-slice2.md) adds recognizable canon subjects to the POV lane. A
canon design must MATCH — text cannot hold exactness (asset routing rule
2026-07-17, EXACTNESS axis) — so a declared character needs reference images
on disk before any LLM spend. This module is that gate, deterministic code
only, mirroring the lane's compiler/render-sheet doctrine:

- ``parse_character_args`` turns the driver's repeated ``--character
  <slug>[:role]`` values into :class:`DeclaredCharacter` records (roles:
  ``protagonist`` — you ARE the subject, only limbs on screen — and
  ``in_frame`` — the subject stands in front of the camera).
- ``check_assets`` looks for ``<refs_root>/<slug>/``. A MISSING/EMPTY
  directory is the operator-hasn't-supplied-yet state: it raises
  :class:`POVAssetRequestNeeded` carrying a role-specific REQUEST SHEET (what
  images to drop, in the research-locked format — RESEARCH-slice2.md §4). A
  PRESENT-but-invalid directory (count out of bounds, non-image file) is a
  defect: plain loud ``ValueError``. On success it returns every reference
  path in DETERMINISTIC UPLOAD ORDER — protagonist characters' refs first
  (declaration order), then in_frame characters' (declaration order), each
  character's files sorted by filename. Upload order defines the ``imageN``
  numbering ticket 11's binding clause uses (the scene lane's
  ``_ordered_refs_by_character`` convention, adapter.py), so this order is a
  CONTRACT, not cosmetics.

The gate runs BEFORE the pitcher/script seats (scripts/pov.py) so a missing
asset never costs an LLM call. Validation is code checks only — no LLM judge
until a real failure proves code checks blind (house rule, PRD-slice2
Implementation Decisions). Role bounds and the image-extension set are module
constants rather than yaml: they are validation plumbing, not prompt grammar
— the render_sheet.py checklist-constant precedent, not the pov_grammar
evidence-row one.
"""

import re
from dataclasses import dataclass
from pathlib import Path

_ALLOWED_ROLES = ("protagonist", "in_frame")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

# Per-role (min, max) reference counts — STARTING bounds, revisited on ticket
# 11's probe evidence. Protagonist: 2-4 crops of what the camera sees
# (PRD-slice2 decision 2 — no face/full-body panels, the camera never shows
# them). in_frame: 2-4 panels per the request sheet's one-face-region recipe
# (mask close-up + full-body + optional 3/4); the corpus's ~3-5 identity-ref
# target (reference-material-playbook.md:118-133) sits inside diminishing
# returns past 3, so 4 is the cap until a watched render argues otherwise.
_ROLE_BOUNDS: dict[str, tuple[int, int]] = {"protagonist": (2, 4), "in_frame": (2, 4)}

# Magic-byte signatures for the allowed extensions — "readable image files"
# (PRD-slice2 asset-gate validation) means the bytes actually open as an
# image format, not merely that the filename ends right; a zero-byte or
# garbage file passing the gate would burn a render slot silently.
# (stdlib imghdr was removed in Python 3.13, hence the manual check.)
def _bytes_look_like_image(head: bytes) -> bool:
    """True iff ``head`` (the file's first 12 bytes) matches PNG/JPEG/WEBP magic."""
    return (
        head.startswith(b"\x89PNG\r\n\x1a\n")
        or head.startswith(b"\xff\xd8\xff")
        or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    )

# seedance_2_0 hard cap: max_image_references: 9 (counts start/end frames
# too) — config/render_rules.yaml limits, measured `model get` 2026-07-06.
# Duplicated as a constant so this gate stays rules-free plumbing; the yaml
# row is the source of truth if they ever disagree.
_MAX_TOTAL_REFS = 9

_REQUEST_COMMON = """\
Source rules (every image, RESEARCH-slice2.md §4):
- NON-PHOTOGRAPHIC official art only: settei/production turnarounds (best),
  official key art / figure renders (second). NEVER live-action screencaps —
  lowest quality tier AND the BUG-012 NSFW-block class.
- ONE design version throughout — refs and prompt must agree on a single
  design or the averaging failure fires (mixed versions = midpoint face class).
- Neutral expression where the art allows a choice (BUG-030: refs beat prompts).
- File types: .png / .jpg / .jpeg / .webp"""

_REQUEST_BY_ROLE = {
    "protagonist": """\
  role: protagonist (you ARE this character — only limbs ever on screen)
  Supply 2-4 CROPS OF WHAT THE CAMERA SEES:
  - suit forearms + gloves, front view
  - suit forearms + gloves, 3/4 view
  - costume detail crop (chest emblem / gauntlet detail) if the design has one
  NO face/mask panel, NO full-body sheet — a ref of what the grammar declares
  unseen risks summoning the character into frame as a separate figure.""",
    "in_frame": """\
  role: in_frame (the character stands in front of the camera, fully visible)
  Supply 2-4 panels, ONE-face-region rule (exactly one panel carries the
  identity-bearing mask/head region at high resolution):
  - mask/head close-up, front (the ONE identity panel)
  - full-body front (proportions + costume)
  - optional: 3/4 view with the head region de-emphasized""",
}


class POVAssetRequestNeeded(Exception):
    """Raised when a declared character has no references on disk yet.

    Not a defect — the operator simply hasn't supplied images. Carries the
    full role-specific request sheet in ``sheet_text``; the driver prints it
    and halts (zero LLM calls made). ``str(exc)`` is the sheet too, so an
    uncaught raise still shows the operator what to do.
    """

    def __init__(self, sheet_text: str) -> None:
        super().__init__(sheet_text)
        self.sheet_text = sheet_text


@dataclass(frozen=True)
class DeclaredCharacter:
    """One ``--character`` declaration: refs-directory slug + visual role."""

    slug: str
    role: str


@dataclass(frozen=True)
class ResolvedCharacter:
    """A gate-validated character: slug, role, and its reference paths in order.

    ``ref_paths`` are filename-sorted within the character; a list of
    ResolvedCharacters from :func:`check_assets` is in UPLOAD ORDER
    (protagonist characters first) — flattening their ``ref_paths`` in
    sequence yields the exact ``imageN`` numbering the compiler's binding
    sentences and ``--image`` flags share.
    """

    slug: str
    role: str
    ref_paths: tuple  # tuple[Path | str, ...] — tuple keeps the record hashable/frozen


def parse_character_args(values: list[str]) -> list[DeclaredCharacter]:
    """Parse repeated ``--character <slug>[:role]`` values.

    Role defaults to ``protagonist`` (the lane's primary content class —
    PRD-slice2 content-class table). Slugs are lowercased (the refs-directory
    convention is lowercase) and validated against ``[a-z0-9_-]``.

    Returns:
        One :class:`DeclaredCharacter` per input value, in DECLARATION ORDER —
        the order is load-bearing: ``check_assets`` uses it (within each role
        group) to build the deterministic upload sequence that defines the
        ``imageN`` numbering downstream.

    Raises:
        ValueError: on an unknown role (message names the allowed roles), a
            malformed slug, or a duplicate slug.
    """
    declared: list[DeclaredCharacter] = []
    seen: set[str] = set()
    for value in values:
        slug, _, role = value.partition(":")
        slug = slug.strip().lower()
        role = role.strip().lower() or "protagonist"
        if not _SLUG_RE.match(slug):
            raise ValueError(
                f"invalid character slug {slug!r} — use lowercase letters, digits, "
                f"underscores, hyphens (it names the refs/<slug>/ directory)"
            )
        if role not in _ALLOWED_ROLES:
            raise ValueError(
                f"unknown role {role!r} for character {slug!r} — allowed roles: "
                f"{', '.join(_ALLOWED_ROLES)}"
            )
        if slug in seen:
            raise ValueError(f"character {slug!r} declared more than once")
        seen.add(slug)
        declared.append(DeclaredCharacter(slug=slug, role=role))
    return declared


def _request_sheet(missing: list[DeclaredCharacter], refs_root: Path) -> str:
    """Compose the operator-facing request sheet for every missing character."""
    blocks = []
    for character in missing:
        blocks.append(
            f"[{character.slug}] drop images into: {refs_root / character.slug}\n"
            f"{_REQUEST_BY_ROLE[character.role]}"
        )
    joined = "\n\n".join(blocks)
    return (
        "REFERENCE ASSETS NEEDED — run halted before any LLM spend.\n\n"
        f"{joined}\n\n{_REQUEST_COMMON}\n\n"
        "Then rerun the same command. Validated references become the permanent\n"
        "library for that character — repeat subjects pass this gate untouched."
    )


def check_assets(
    characters: list[DeclaredCharacter], refs_root: str | Path
) -> list[ResolvedCharacter]:
    """Validate every declared character's references; return them upload-ordered.

    Returns:
        One :class:`ResolvedCharacter` per declared character, in
        deterministic upload order — protagonist characters first
        (declaration order), then in_frame characters (declaration order),
        each character's files filename-sorted. Flattening their
        ``ref_paths`` in sequence defines the ``imageN`` numbering the
        compiler's binding sentences and ``--image`` flags share (module
        docstring).

    Raises:
        POVAssetRequestNeeded: if any declared character's directory is
            missing or empty — sheet_text lists EVERY missing character so
            the operator sources them all in one pass, not one rerun each.
        ValueError: if a present directory fails validation — reference
            count outside the role's bounds, a non-image file in the
            directory, unreadable image bytes, or the total across
            characters exceeding the measured CLI cap.
    """
    root = Path(refs_root)
    missing = [
        c for c in characters
        if not (root / c.slug).is_dir() or not any((root / c.slug).iterdir())
    ]
    if missing:
        raise POVAssetRequestNeeded(_request_sheet(missing, root))

    per_character: dict[str, list[Path]] = {}
    for character in characters:
        char_dir = root / character.slug
        files = sorted(p for p in char_dir.iterdir() if p.is_file())
        strangers = [p.name for p in files if p.suffix.lower() not in _IMAGE_EXTENSIONS]
        if strangers:
            raise ValueError(
                f"refs/{character.slug}/ contains non-image file(s): "
                f"{', '.join(strangers)} — allowed extensions: "
                f"{', '.join(sorted(_IMAGE_EXTENSIONS))}"
            )
        unreadable = [
            p.name for p in files if not _bytes_look_like_image(p.read_bytes()[:12])
        ]
        if unreadable:
            raise ValueError(
                f"refs/{character.slug}/ contains file(s) whose bytes are not a "
                f"readable PNG/JPEG/WEBP image: {', '.join(unreadable)} — a corrupt "
                f"or empty reference would silently burn a render"
            )
        low, high = _ROLE_BOUNDS[character.role]
        if not (low <= len(files) <= high):
            raise ValueError(
                f"character {character.slug!r} ({character.role}) has {len(files)} "
                f"reference(s); the role needs {low}-{high} (request-sheet spec)"
            )
        per_character[character.slug] = files

    ordered = [
        ResolvedCharacter(
            slug=character.slug,
            role=character.role,
            ref_paths=tuple(per_character[character.slug]),
        )
        for role in _ALLOWED_ROLES
        for character in characters
        if character.role == role
    ]
    total = sum(len(c.ref_paths) for c in ordered)
    if total > _MAX_TOTAL_REFS:
        raise ValueError(
            f"{total} total references across characters exceeds the "
            f"seedance_2_0 cap of {_MAX_TOTAL_REFS} images (render_rules.yaml "
            f"limits.max_image_references, measured) — trim the libraries"
        )
    return ordered
