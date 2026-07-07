"""
Character-sheet generator (spec 2026-07-06 Workstream B — replaces the parked
YouTube reference harvester, D8).

Takes ONE user-hand-picked seed image of a character and generates the
3-angle reference sheet the render lane needs — front / three-quarter /
profile — as separate PNGs in ``refs/<character_slug>/``. That folder name IS
the binding: the render adapter attributes refs to cast members by parent
folder (path convention, locked 2026-07-06), and the slug here uses the same
normalization as the adapter's ``_slug`` (lowercase, spaces to underscores).

Model: GPT Image 2 by default (doc 15 L118-120: author-recommended over
nano-banana for multi-angle character work; exact CLI id ``gpt_image_2``
verified via ``higgsfield model get`` 2026-07-06). ``--model nano_banana_2``
is the fallback.

Why 3 separate generations instead of one sheet image: the adapter uploads
individual files and binds them positionally ("(imageN)"); a single grid
sheet would need cropping and risks the model reading the grid itself as
composition. 3 angles is the coverage knee (reference-material-playbook
L66-77: front → ¾ (highest-information view) → profile).

SEED QUALITY WARNING (doc 15 L122): a blurry or non-front-facing seed makes
the model INVENT detail on the angles it has to extrapolate — those
inventions then become canon across every render. Pick a sharp, front-facing,
well-lit seed.

Cost: ~2cr per generation (nano-banana measured 2cr on billing 2026-07-06;
GPT Image 2 assumed comparable until billed) → ~6cr per 3-angle sheet.
Stated before any paid call; interactive 'yes' gate (ADR-0007 / L7).

USAGE:
  uv run python scripts/make_char_sheet.py --seed render_taste_test/wistoria_refs/will_2_adult.png --character "Will"
  uv run python scripts/make_char_sheet.py --seed elfie.png --character "Elfie" --model nano_banana_2

OUTPUT:
  refs/<slug>/front.png, refs/<slug>/three_quarter.png, refs/<slug>/profile.png
  — printed at the end ready to paste into smoke_content_writer --refs.
  User eyeballs the 3 images (the approval gate is a glance).
"""

import argparse
import sys
from pathlib import Path

# Repo root on sys.path — scripts run as files, not as a package (same pattern
# as scripts/label.py).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv("config/.env")

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Reuse the executor's CLI/download seam (the project's one Higgsfield-CLI
# boundary — same pattern as HiggsfieldTTS).
from src.generation.executor import _download, _extract_url, _run_cli, _sanitize_prompt  # noqa: E402

EST_CREDITS_PER_IMAGE = 2  # nano-banana measured 2cr (billing 2026-07-06); GPT Image 2 assumed comparable

# Angle prompts: same character, neutral expression, matched flat lighting
# (playbook L66-77 — a smiling ref mixed with a neutral one averages into a
# "midpoint face"), clean background (doc 15 L107-110 base prompt).
_ANGLES: dict[str, str] = {
    "front": "a front-facing full-body view",
    "three_quarter": "a three-quarter view, body and face turned about 45 degrees",
    "profile": "a left profile view, face and body fully side-on",
}


def _slug(name: str) -> str:
    """Match src/generation/render_adapters/adapter._slug exactly — the folder
    name this writes is what the adapter binds refs by."""
    return name.strip().lower().replace(" ", "_")


def _angle_prompt(angle_description: str, character: str) -> str:
    """Compose one angle's generation prompt from the doc-15 multi-angle base."""
    return (
        f"Create {angle_description} of this exact character ({character}). "
        "Keep the identical face, hairstyle, outfit, colors and art style as "
        "the reference image. Neutral expression, arms relaxed at the sides, "
        "flat even lighting, clean white background, no text, no watermark."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a 3-angle character reference sheet from one seed image."
    )
    parser.add_argument("--seed", required=True, help="Path to ONE sharp, front-facing seed image.")
    parser.add_argument("--character", required=True, help='Character name, e.g. "Will" — becomes refs/<slug>/.')
    parser.add_argument(
        "--model", default="gpt_image_2",
        help="Image model CLI id (default gpt_image_2; fallback nano_banana_2).",
    )
    parser.add_argument("--yes", action="store_true", help="Skip the interactive spend confirmation.")
    args = parser.parse_args()

    seed = Path(args.seed)
    if not seed.exists():
        raise SystemExit(f"Seed image not found: {seed}")

    out_dir = Path("refs") / _slug(args.character)
    total = EST_CREDITS_PER_IMAGE * len(_ANGLES)
    print(
        f"Sheet for {args.character!r}: {len(_ANGLES)} generations on {args.model} "
        f"~{EST_CREDITS_PER_IMAGE}cr each = ~{total}cr total -> {out_dir}/"
    )
    print(
        "SEED QUALITY: if the seed is blurry or not front-facing, the model "
        "INVENTS detail on extrapolated angles and those inventions become "
        "canon in every render (doc 15 L122). Seed: " + str(seed)
    )
    if not args.yes:
        answer = input(f"Spend ~{total} credits? Type 'yes' to proceed: ")
        if answer.strip().lower() != "yes":
            raise SystemExit("Aborted — nothing spent.")

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for angle, description in _ANGLES.items():
        print(f"[{angle}] generating...")
        output = _run_cli([
            "higgsfield", "generate", "create", args.model,
            "--prompt", _sanitize_prompt(_angle_prompt(description, args.character)),
            "--aspect_ratio", "3:4",
            "--image", str(seed),
            "--wait",
        ])
        path = _download(_extract_url(output), str(out_dir / f"{angle}.png"))
        written.append(path)
        print(f"[{angle}] -> {path}")

    print("\nSheet complete — EYEBALL these before rendering (the approval gate):")
    for path in written:
        print(f"  {path}")
    print("\nPaste into the smoke run:\n  --refs " + " ".join(written))


if __name__ == "__main__":
    main()
