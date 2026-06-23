"""
End-to-end smoke for the single-shot pipeline (premise → write → render_jobs → execute).

By default runs dry_run (cost estimate only, no credits spent). Pass --real to
execute a live Higgsfield render. A premise is auto-generated via PremiseGenerator
(n=1) unless --premise supplies one manually.

USAGE:
  uv run python scripts/smoke_content_writer.py                     # dry run, auto premise
  uv run python scripts/smoke_content_writer.py --premise "..."     # dry run, named premise
  uv run python scripts/smoke_content_writer.py --real              # LIVE render (~60cr)
  uv run python scripts/smoke_content_writer.py --real --model veo3_1 --premise "..."

OUTPUT:
  Prints the full ContentPackage (still prompt, motion prompt, hook text, caption,
  hashtags, credit estimate). In --real mode also prints the local still/clip paths
  and whether the clip carries native audio.
  A timestamped transcript of the run is saved to output/smoke_runs/.
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("config/.env")

from src.generation.content_writer import ContentWriter  # noqa: E402
from src.generation.executor import execute  # noqa: E402
from src.generation.premise_generator import PremiseGenerator  # noqa: E402
from src.generation.render_adapters.adapter import render_jobs  # noqa: E402
from src.generation.render_adapters.rules import RenderRules  # noqa: E402


class _Tee:
    """Duplicate every write to two streams (live console + the record file)."""

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)

    def flush(self):
        for s in self._streams:
            s.flush()


def _git_sha() -> str:
    """Return the current short git SHA, or 'nogit' if unavailable."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "nogit"


def main() -> None:
    """Parse args, run the single-shot pipeline, print the package and render result."""
    parser = argparse.ArgumentParser(
        description="End-to-end smoke for the single-shot pipeline."
    )
    parser.add_argument(
        "--premise",
        default=None,
        help="One-line premise to develop. Omit to auto-generate via PremiseGenerator.",
    )
    parser.add_argument(
        "--model",
        default="veo3_1",
        help="Motion model CLI id (default: veo3_1).",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="Run a live Higgsfield render. Default is dry_run (cost estimate only).",
    )
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sha = _git_sha()
    record_path = Path("output/smoke_runs") / f"smoke_{ts}_{sha}.txt"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_file = record_path.open("w", encoding="utf-8")
    record_file.write(f"# smoke_content_writer run\n# timestamp: {ts}\n# git_sha: {sha}\n\n")
    record_file.flush()

    original_stdout = sys.stdout
    sys.stdout = _Tee(original_stdout, record_file)

    try:
        # --- Premise ---
        if args.premise:
            premise = args.premise
            print(f"[premise] (supplied)\n{premise}\n")
        else:
            print("[premise] generating via PremiseGenerator (n=1)…")
            premise_set = PremiseGenerator().generate(n=1)
            premise = premise_set.premises[0].premise
            why = premise_set.premises[0].why_arresting
            print(f"  {premise}")
            if why:
                print(f"  -> {why}")
            print()

        # --- Write ---
        rules = RenderRules()
        print(f"[write] model={args.model}")
        package = ContentWriter().write(
            premise,
            rules=rules,
            model_cli_id=args.model,
        )

        # --- Package dump ---
        print("=" * 70)
        print(f"PREMISE:       {package.premise}")
        print(f"MODEL:         {package.model_cli_id}")
        print(f"MOOD ANCHOR:   {package.mood_anchor}")
        print("-" * 70)
        print(f"START KEYFRAME:\n  {package.shot.start_keyframe}")
        print(f"\nMOTION:\n  {package.shot.motion}")
        if package.shot.end_keyframe:
            print(f"\nEND KEYFRAME:\n  {package.shot.end_keyframe}")
        print("-" * 70)
        print(f"HOOK TEXT:     {package.onscreen_text}")
        print(f"CAPTION:       {package.caption}")
        print(f"HASHTAGS:      {package.hashtags}")
        if package.voiceover:
            print(f"VOICEOVER:     {package.voiceover}")
        if package.rationale:
            print(f"RATIONALE:     {package.rationale}")
        print("=" * 70 + "\n")

        # --- Render jobs + execute ---
        jobs = render_jobs(package, rules)
        out_dir = str(Path("output/smoke_runs") / f"render_{ts}_{sha}")

        mode = "REAL RENDER" if args.real else "DRY RUN (cost estimate only)"
        print(f"[execute] {mode}")
        result = execute(jobs, out_dir, dry_run=not args.real)

        print("\n[result]")
        print(f"  credits_spent: {result.credits_spent}")
        if args.real:
            print(f"  still_path:    {result.still_path}")
            print(f"  clip_path:     {result.clip_path}")
            print(f"  has_audio:     {result.has_audio}")

    finally:
        sys.stdout = original_stdout
        record_file.close()
        print(f"\n[record saved] {record_path}")


if __name__ == "__main__":
    main()
