"""
Generate a slate of imagination-driven content premises (ideation front-end).

No archive, no DB, no miner recipe — pure LLM invention from the standing brief
in PremiseGenerator. Read the slate and eye-filter the best premise to hand to
scripts/smoke_content_writer.py (or ContentWriter.write directly).

USAGE:
  uv run python scripts/generate_premises.py
  uv run python scripts/generate_premises.py --n 5
"""

import argparse

from dotenv import load_dotenv

load_dotenv("config/.env")

from src.generation.premise_generator import PremiseGenerator  # noqa: E402


def main() -> None:
    """Parse args, generate n imagination premises, and print them numbered."""
    parser = argparse.ArgumentParser(
        description="Generate imagination-driven video premises (no DB required)."
    )
    parser.add_argument(
        "--n",
        type=int,
        default=10,
        help="How many premises to generate (default: 10).",
    )
    args = parser.parse_args()

    result = PremiseGenerator().generate(n=args.n)

    print(f"\n{len(result.premises)} imagination premises:\n")
    for i, p in enumerate(result.premises, 1):
        print(f"{i}. {p.premise}")
        if p.why_arresting:
            print(f"   → {p.why_arresting}")
        print()


if __name__ == "__main__":
    main()
