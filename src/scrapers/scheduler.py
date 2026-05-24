"""
RQ dispatcher that enqueues one run_niche_scrape job per active niche.

Replaces the old APScheduler glue (which ran scrapes inline in the
FastAPI process). Now start() enqueues to the default RQ queue and
returns immediately — a separate `rq worker` process executes the jobs.
"""

from sqlalchemy import select

from src.database import SessionLocal
from src.models.niche import Niche
from src.scrapers.recurring import run_niche_scrape

from rq import Queue
from redis import Redis

def get_redis_connection() -> Redis:
    """
    Return a Redis client connected to localhost:6379.

    Host and port are hardcoded for local dev. Task 6 will wire these
    to config/settings.yaml scrape.recurring keys.
    """
    return Redis(host="localhost", port=6379)

def dispatch_all_niches() -> list[str]:
    """
    Enqueue one run_niche_scrape job per active niche into the default RQ queue.

    Opens a DB session to query active niches, enqueues each, then closes the
    session. Does not wait for jobs to complete — fire and forget.

    Returns:
        List of RQ job ID strings, one per enqueued niche.
    """
    db = SessionLocal()
    niches = db.execute(select(Niche).where(Niche.is_active == True)).scalars().all()

    queue = Queue(connection=get_redis_connection())

    job_ids = []
    for niche in niches:
        job = queue.enqueue(run_niche_scrape, niche.id)
        job_ids.append(job.id)

    db.close()

    return job_ids 


def start() -> None:
    """
    Dispatch all active-niche scrape jobs to the RQ queue and log the count.

    Called from FastAPI lifespan on startup. Returns immediately — actual
    execution happens in the RQ worker process.
    """
    jobs = dispatch_all_niches()
    print(f"[scheduler] enqueued {len(jobs)} niche scrape jobs")

def stop() -> None:
    """
    No-op. RQ worker lifecycle is managed externally (systemd/tmux/rq worker CLI).

    Kept for API compatibility with the old APScheduler-based scheduler.
    """
    print("[scheduler] RQ worker manages its own lifecycle — no-op")


