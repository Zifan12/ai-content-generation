import argparse
import statistics
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.database import SessionLocal
from src.models.blueprint import BlueprintRecord
from src.models.published_video import PublishedVideo


def rank_percentiles(values: list) -> list[float]:
    """
    Self-relative rank percentile of each value, in the input's original order.

    Worst value -> 0.0, best -> 1.0. Ties share the average of the ranks they occupy
    (e.g. [100, 50, 50, 200] -> [0.667, 0.167, 0.167, 1.0]).

    Degenerate case: a single value has no relative signal, so it returns [0.5] (neutral
    "median"), avoiding a divide-by-(n-1)=0. An empty list returns [].
    """
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [0.5]

    sorted_values = sorted(values)

    result = []
    for v in values:
        positions = [i for i, x in enumerate(sorted_values) if x == v]
        result.append(statistics.mean(positions) / (n - 1))

    return result


def write_back_percentiles(session: Session, niche: str | None = None) -> int:
    """
    Compute self-relative percentiles over all measured posts and write them to blueprints.

    Loads every PublishedVideo with a non-null view_7d (optionally filtered to one niche),
    ranks their view_7d via rank_percentiles, and writes each post's percentile to the linked
    BlueprintRecord.outcome_view_percentile. Returns the number of posts scored.

    This is the batch pass — run once after all ~30 posts have day-7 counts (a percentile over
    a tiny set is noise). If two posts share one blueprint (rare — each blueprint normally
    conditions one video), last-write-wins on that blueprint's column.
    """
    query = session.query(PublishedVideo).filter(PublishedVideo.view_7d.isnot(None))
    if niche is not None:
        query = query.filter(PublishedVideo.niche == niche)
    posts = query.all()

    if not posts:
        return 0

    percentiles = rank_percentiles([p.view_7d for p in posts])

    for post, pct in zip(posts, percentiles):
        blueprint = session.get(BlueprintRecord, post.blueprint_id)
        if blueprint is not None:
            blueprint.outcome_view_percentile = pct

    session.commit()
    return len(posts)


def main() -> None:
    """Open a real Postgres session, run the batch write-back, print how many posts were scored."""
    parser = argparse.ArgumentParser(
        description="Compute self-relative view percentiles and write them back to blueprints."
    )
    parser.add_argument("--niche", default=None, help="Restrict to one niche (optional).")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        n = write_back_percentiles(session, niche=args.niche)
        print(f"Scored {n} posts; wrote outcome_view_percentile to their blueprints.")
    finally:
        session.close()


if __name__ == "__main__":
    main()

