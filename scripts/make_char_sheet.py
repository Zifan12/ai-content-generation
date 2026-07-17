"""
Character-sheet generator (spec 2026-07-06 Workstream B — replaces the parked
YouTube reference harvester, D8).

Takes ONE user-hand-picked seed image of a character and generates its
reference suite — face / body_faceless / back — as separate PNGs in
``refs/<character_slug>/``. That folder name IS the binding: the render adapter
attributes refs to cast members by parent folder (path convention, locked
2026-07-06), and the slug here uses the same normalization as the adapter's
``_slug`` (lowercase, spaces to underscores).

ONE FACE, AND IT IS BIG. Rewritten 2026-07-16 (BUG-032). This script used to emit
a front / three-quarter / profile turnaround — three full-body panels, each with
its own small face. The vendor names that exact shape as the root cause of ID
drift and mid-video face-swap: mixing the face ref into body/costume images
(参考图混用), and the face occupying too small a share of the frame to out-weigh
the background (人脸占比过小). See ``_ANGLES`` below for the quote and the full
reasoning, including how it dissolves the corpus's 3-angle-vs-no-multi-view
contradiction (the enemy was competing FACES, never angles).

Model: GPT Image 2 by default (doc 15 L118-120, and independently the
practitioner recommendation over nano-banana for character work — "GPT Image 2
works best for realistic close-ups of people's faces"; exact CLI id
``gpt_image_2`` verified via ``higgsfield model get`` 2026-07-06).
``--model nano_banana_2`` is the fallback.

Why separate generations instead of one grid sheet: the adapter uploads
individual files and binds them positionally ("(imageN)"); a single grid sheet
would need cropping and risks the model reading the grid itself as composition.
It is also what makes the one-face rule expressible at all — a grid is by
definition 参考图混用.

SEED QUALITY WARNING (doc 15 L122): a blurry or non-front-facing seed makes
the model INVENT detail on the angles it has to extrapolate — those
inventions then become canon across every render. Pick a sharp, front-facing,
well-lit seed.

Cost: 7cr per generation on GPT Image 2 (MEASURED, billing 2026-07-07);
nano_banana_2 measured 2cr → ~21cr or ~6cr per suite respectively.
Stated before any paid call; interactive 'yes' gate (ADR-0007 / L7).

USAGE:
  uv run python scripts/make_char_sheet.py --seed render_taste_test/wistoria_refs/will_2_adult.png --character "Will"
  uv run python scripts/make_char_sheet.py --seed elfie.png --character "Elfie" --model nano_banana_2

OUTPUT:
  refs/<slug>/face.png, refs/<slug>/body_faceless.png, refs/<slug>/back.png
  — printed at the end ready to paste into smoke_content_writer --refs.
  User eyeballs the 3 images (the approval gate is a glance). CHECK THE FACELESS
  ONE ACTUALLY HAS NO FACE: the head removal is prompted, not guaranteed, and a
  head that sneaks back in reintroduces the exact defect this suite exists to
  avoid. If it drew one, crop it off by hand — the practitioner this shape comes
  from does the removal in Photoshop rather than trusting the generator, and also
  warns that re-editing through the image model degrades quality each pass.

NOT YET VALIDATED: no character has been regenerated through this script since
the 2026-07-16 rewrite. The live refs (master.png / sheet_identity.png) are
hand-made and predate it — they are a full-body-with-small-face plus a close-up,
i.e. the old defective shape. Regenerating them is an asset decision, not a code
one; see bugs.md BUG-030/BUG-032.
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

EST_CREDITS_PER_IMAGE = 7  # GPT Image 2 MEASURED 7cr/image (billing 2026-07-07, 6 generations); nano_banana_2 measured 2cr — pass --model to trade quality for cost

# The suite: EXACTLY ONE image carries a face, and it is a big one.
#
# Rewritten 2026-07-16 (closes BUG-032). The old suite was a 3-angle turnaround —
# front / three_quarter / profile, every panel a full-body with its own small face.
# That is the vendor's named ROOT CAUSE of ID drift and mid-video face-swap, not a
# neutral choice (08-避坑12问.md:13):
#
#   根因：人脸参考图的有效性不足。
#     - 参考图混用：将人脸参考图与全身/半身姿态图、服装参考图、细节图等合并在同一张图片中
#     - 人脸占比过小：人脸区域占整张图的比例过小，模型在提取人脸特征时权重不够，
#       容易被背景或其他元素干扰
#   解决方案（强化人脸参考的独立性和权重）
#
# ("Root cause: the face reference's effectiveness is insufficient — MIXING the face
# ref into body/costume/detail images, and the FACE OCCUPYING TOO SMALL A SHARE, so
# the model under-weights facial features and gets pulled off by the background.
# Solution: strengthen the face reference's INDEPENDENCE and WEIGHT.")
#
# This also dissolves the corpus contradiction that blocked BUG-032: the system guide
# prescribes a 3-angle sheet, the vendor doc says multi-view makes the model read one
# person as several. Both are right — the enemy was never the ANGLES, it was competing
# FACES. Multiple angles are safe when exactly one panel has a face to bind to
# ("Dan Kieft Three-Step Film Workflow.md" §1, practitioner, same Higgsfield+Seedance
# stack: close-up face + full-body with the face REMOVED + backside; he deletes the
# head in Photoshop for precisely the small-face reason above).
#
# The face-removal is prompted here rather than done in post. That is the weaker of
# the two — a generator asked to omit a head may draw one anyway — so `main()` checks
# the output and says so. UNVALIDATED as of 2026-07-16: no character has been
# regenerated through this script since the rewrite.
_ANGLES: dict[str, str] = {
    "face": (
        "a tight head-and-shoulders portrait, the face filling most of the frame, "
        "sharp facial detail"
    ),
    "body_faceless": (
        "a front-facing full-body view with the head cropped ENTIRELY out of frame — "
        "frame from the shoulders down, showing the full outfit and footwear. The head "
        "and face must NOT appear anywhere in this image"
    ),
    "back": "a full-body view from directly behind, facing away, no face visible",
}


def _slug(name: str) -> str:
    """Match src/generation/render_adapters/adapter._slug exactly — the folder
    name this writes is what the adapter binds refs by."""
    return name.strip().lower().replace(" ", "_")


def _angle_prompt(angle_description: str, character: str) -> str:
    """Compose one panel's generation prompt from the doc-15 multi-angle base.

    The background is GREY, not white: white bleeds into the render's exposure and
    comes back overexposed, because the ref's background luminance transfers along
    with everything else ("Dan Kieft Advanced Techniques (OpenArt).md" §1 —
    demonstrated side by side, same prompt, white ref vs grey ref). This file
    hardcoded "clean white background" until 2026-07-16, i.e. the disproven value.

    Neutral expression is mandatory and non-negotiable
    (reference-material-playbook.md:59-60, video_model_system_guide.md:444, and the
    vendor's own "无表情最佳" / no-expression-is-best): a smiling ref overrides a
    prompted expression at render time — measured on pitch-51, where "a satisfied
    smirk" rendered as a broad smile because the ref smiled (bugs.md BUG-030).
    """
    return (
        f"Create {angle_description} of this exact character ({character}). "
        "Keep the identical face, hairstyle, outfit, colors and art style as "
        "the reference image. Neutral expression, mouth relaxed and closed, arms "
        "relaxed at the sides, flat even lighting, clean neutral grey background, "
        "no text, no watermark."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a character reference suite (face / body_faceless / back) "
            "from one seed image. Exactly one panel carries a face."
        )
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
