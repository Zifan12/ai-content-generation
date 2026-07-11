"""
Generate a cached world-anchor description for a location, from its screencap.

Location grounding (spec 2026-07-10, decision #4): the setting is grounded by a
canon screencap PLUS a short prose world-anchor that MUST match the picture. To
guarantee the match, the description is VISION-generated from the screenshot
itself (not web-researched or hand-invented, either of which can contradict the
image), then cached in the location folder and reused by every render set in
that location — this is a one-time step, never the per-render hot path.

WHAT IT DOES:
  refs/_location/<slug>/<image>  --(Gemini Flash vision, seat 'location_anchor')-->
  ~40-60 words of concrete setting nouns  -->  refs/_location/<slug>/world_anchor.txt

The adapter later appends that text verbatim as the scene prompt's setting block
and binds the screencap as a non-character "(imageN)" ref.

USAGE:
  uv run python scripts/gen_location_anchor.py --slug elfie_bedroom
  uv run python scripts/gen_location_anchor.py --slug elfie_bedroom --force   # overwrite existing

Running on a slug that already has world_anchor.txt refuses unless --force, so a
hand-curated description (e.g. the Opus-vision paragraph seeded during design) is
not clobbered by accident. Cost ~= one Gemini-Flash vision call (~$0.0002).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv("config/.env")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pydantic import BaseModel, ConfigDict  # noqa: E402

from src.providers.llm.factory import llm_for_seat  # noqa: E402

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}

_VISION_PROMPT = (
    "Describe THIS location for a video-generation prompt in 40-60 words. "
    "List only concrete, visible nouns: architecture, materials, furniture, "
    "fixtures, light sources, and the overall palette and mood. Describe the "
    "SPACE only — no characters, no people, no story, no camera direction. "
    "Output a single flowing description, no headings or lists."
)


class WorldAnchor(BaseModel):
    """Structured-output envelope for the vision call: just the anchor text.

    A one-field model so the seat returns validated JSON (the parse() contract)
    rather than free prose; ``description`` is written verbatim to world_anchor.txt.
    """

    model_config = ConfigDict(extra="forbid")

    description: str


def find_location_image(folder: Path) -> Path:
    """Return the single location screencap in a location folder.

    Picks the first image file (png/jpg/jpeg, sorted by name) so the choice is
    deterministic. Exits loudly if the folder is missing or holds no image — a
    mistyped slug should fail here, not produce an empty anchor.

    Args:
        folder: The refs/_location/<slug>/ directory.

    Returns:
        Path to the screencap to describe.

    Raises:
        SystemExit: folder absent, or no image file present.
    """
    if not folder.is_dir():
        raise SystemExit(f"No location folder {folder} — check the slug.")
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in _IMAGE_SUFFIXES)
    if not images:
        raise SystemExit(f"No image file in {folder} — need a room screencap.")
    return images[0]


def main() -> None:
    """Generate and cache the world-anchor text for one location slug."""
    parser = argparse.ArgumentParser(description="Vision-generate a location world-anchor.")
    parser.add_argument(
        "--slug",
        required=True,
        help="Location folder name under refs/_location/ (e.g. elfie_bedroom).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing world_anchor.txt (default: refuse, to protect "
        "a hand-curated description).",
    )
    args = parser.parse_args()

    folder = Path("refs/_location") / args.slug
    image = find_location_image(folder)
    out_path = folder / "world_anchor.txt"
    if out_path.exists() and not args.force:
        raise SystemExit(
            f"{out_path} already exists — pass --force to regenerate (this would "
            "overwrite the current description)."
        )

    print(f"[vision] describing {image} via seat 'location_anchor'")
    anchor = llm_for_seat("location_anchor").parse(
        _VISION_PROMPT,
        WorldAnchor,
        images=[str(image)],
    )
    text = anchor.description.strip()

    out_path.write_text(text + "\n", encoding="utf-8")
    print(f"[written] {out_path}  ({len(text.split())} words)")
    print("-" * 70)
    print(text)


if __name__ == "__main__":
    main()
