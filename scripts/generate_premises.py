"""
Generate five data-grounded content premises for a niche (ideation front-end).

WHY THIS EXISTS:
  The writer needs a premise (the WHAT — the subject to develop) that nothing in the
  pipeline auto-produced. This CLI closes that gap: it reads the top-performing videos
  for a niche, hands them + the latest miner recipe to the PremiseGenerator, and prints
  five fresh premises that reuse a proven mechanic on a brand-new subject. You eyeball
  the five, pick one, and feed it into the writer (Task 6).

USAGE:
  uv run python -m scripts.generate_premises --niche surreal_hyperreal
  uv run python -m scripts.generate_premises --niche surreal_hyperreal --k 20

DESIGN:
  The sourcing + generation logic lives in generate_premises(session, niche, k) which
  takes a session passed in — so it stays unit-testable against in-memory SQLite. The
  argparse wrapper (main) is the only part that opens a real Postgres SessionLocal and
  formats the printed output. This is the logic/CLI split reused across the project's
  CLIs (see scripts/record_post.py).

PREREQUISITES:
  - The D: archive must be ingested (scripts.ingest_archive) so _top_winners has a pool.
  - A miner run must exist for the niche (miner_rankings) so latest_run returns a
    candidate. If no run exists, generate_premises must fail loud, not silently feed an
    empty recipe to the LLM.
"""

import argparse

from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.schemas.premise import PremiseSet
from src.generation.premise_generator import PremiseGenerator
from src.miner.storage import latest_run


def generate_premises(db: Session, niche: str, k: int) -> PremiseSet:
    """
    Source the top miner candidate for the niche, then generate five premises grounded
    on the niche's top-k winning videos.

    Steps you implement:
      1. Pull the most recent ranked candidates for the niche via latest_run(session, niche).
      2. Decide which candidate to use as the mechanics recipe (the ranked list is ordered
         by rank — rank 1 is the strongest combo). Handle the empty case: if latest_run
         returns [], there is no recipe — raise a clear error telling the operator to run
         the miner first (mirror the writer's "must be grounded" guard, with a message that
         names the actual cause).
      3. Construct a PremiseGenerator and call .generate(candidate, session, niche, k).
      4. Return the PremiseSet.

    Args:
        session: an open SQLAlchemy session (caller owns its lifecycle).
        niche: the niche name to ground on (must match a Niche.name and a miner run's
            niche_label).
        k: how many top winners to feed the generator as evidence.

    Returns:
        A validated PremiseSet of exactly five premises.

    Raises:
        ValueError: if no miner run exists for the niche (no recipe to ground on).
    """
    ranked_candidates = latest_run(db, niche)

    if not ranked_candidates:
        raise ValueError("Ranked Candidates is empty")
    
    chosen_candidate = ranked_candidates[0]

    return PremiseGenerator().generate(chosen_candidate, db, niche, k)


def main() -> None:
    """
    Parse CLI args, open a real Postgres session, generate five premises, and print them
    numbered with their echoed mechanic and copies-nothing justification so the operator
    can eyeball and pick one.
    """
    parser = argparse.ArgumentParser(
        description="Generate five data-grounded content premises for a niche."
    )
    parser.add_argument(
        "--niche",
        default="surreal_hyperreal",
        help="Niche to ground on (must match a Niche.name and a miner run's niche_label).",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=12,
        help="How many top-by-views winners to feed the generator as evidence.",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        result = generate_premises(session, args.niche, args.k)
    finally:
        session.close()

    print(f"\nFive grounded premises for niche '{args.niche}':\n")
    for i, premise in enumerate(result.premises, 1):
        print(f"{i}. {premise.premise}")
        print(f"   mechanic:  {premise.winning_mechanics}")
        print(f"   diverges:  {premise.copies_nothing}\n")


if __name__ == "__main__":
    main()
