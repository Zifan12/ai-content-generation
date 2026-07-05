import datetime
import asyncio
import logging
import time
import json 

from sqlalchemy import select
from typing import Callable 
from sqlalchemy.orm import Session

from src.scrapers.tiktok import TikTokScraper
from src.database import SessionLocal
from src.models.niche import Niche
from src.models.transcript import Transcript  
from src.blueprints.extractor import BlueprintExtractor
from src.models.extractor_response import ExtractorResponse
from src.blueprints.pricing import compute_response_cost
from src.providers.llm.factory import llm_for_seat

class BudgetExceeded(Exception): 
    pass 

DEFAULT_MAX_DAILY_SPEND = 1.00

def _get_transcript_text(db, content_item_id) -> str | None:
    stmt = (
        select(Transcript.text)
        .where(Transcript.content_item_id == content_item_id)
    )
    return db.scalar(stmt)

def today_extraction_spend(db) -> float:
    """
    Sum LLM extraction cost for all ExtractorResponse rows created today (UTC).

    Used by the budget guard to account for spend from prior RQ jobs in the
    same calendar day, not just the current job's in-memory accumulator.

    Args:
        db: Active SQLAlchemy session.

    Returns:
        Total USD spent on extractions since UTC midnight today.
    """
    today_midnight = datetime.datetime.now(datetime.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(
        select(ExtractorResponse).where(ExtractorResponse.created_at >= today_midnight)
    ).scalars().all()
    return sum(compute_response_cost(r) for r in rows)


def run_niche_scrape(niche_id: int, session_factory: Callable[[], Session] = SessionLocal) -> dict:
    """
    Scrape trending TikTok videos for one niche and extract Blueprints.

    Fetches up to 50 videos via Apify, upserts to RawContentItem, then
    runs Blueprint extraction for each item — hitting the LLM cache first,
    calling the extractor only on cache misses. Raises BudgetExceeded if the
    day's extraction spend (cross-job, from ExtractorResponse rows) exceeds
    DEFAULT_MAX_DAILY_SPEND before a new extraction can start.

    Args:
        niche_id: PK of the niche row to scrape.
        session_factory: Callable returning a SQLAlchemy Session. Injectable
            for testing without touching the real database.

    Returns:
        Result dict with keys: niche_id, niche_name, items_scraped,
        items_inserted, items_updated, items_extracted, items_cache_hit,
        extraction_usd_spent, started_at, completed_at, error.

    Raises:
        BudgetExceeded: If daily spend cap is hit mid-loop. Partial result
            attached as exc.partial_result.
    """

    started_at = datetime.datetime.now(datetime.UTC).isoformat()
    start_time = time.perf_counter()

    result = {
        "niche_id": niche_id,
        "niche_name": "",
        "items_scraped": 0,
        "items_inserted": 0,
        "items_updated": 0,
        "items_extracted": 0,
        "items_cache_hit": 0,
        "extraction_usd_spent": 0.0,
        "started_at": started_at,
        "completed_at": "",
        "error": None,
    }

    try:
        with session_factory() as db:
            niche = db.execute(select(Niche).where(Niche.id == niche_id)).scalar_one_or_none()
            if niche is None:
                raise ValueError(f"Niche id={niche_id} not found")
            result["niche_name"] = niche.name

            scraper = TikTokScraper(db)

            result_tuple = asyncio.run(scraper.fetch_trending(niche_id=niche_id, query=niche.hashtag_seeds, max_results=50))
            items, inserted, updated = result_tuple
            result["items_scraped"] = len(items)
            result["items_inserted"] = inserted
            result["items_updated"] = updated

            extractor = BlueprintExtractor(llm=llm_for_seat("blueprint_extractor"))

            for item in items:
                transcript = _get_transcript_text(db, item.id)
                bp = extractor.reparse_from_cache(item, transcript, niche.name, db)

                if bp is not None:
                    result["items_cache_hit"] += 1
                else:
                    # Recompute per iteration: each extract() adds an ExtractorResponse row,
                    # so the spend visible to subsequent items grows within a single job.
                    # A single pre-loop check would miss budget exhaustion mid-batch.
                    today_spending = today_extraction_spend(db)
                    if today_spending >= DEFAULT_MAX_DAILY_SPEND:
                        raise BudgetExceeded(f"Daily spend ${today_spending:.4f} exceeded ${DEFAULT_MAX_DAILY_SPEND:.2f}")
                    
                    bp = extractor.extract(item, transcript, niche.name, db)
                    stmt = (
                        select(ExtractorResponse)
                        .where(ExtractorResponse.content_item_id == item.id)
                        .order_by(ExtractorResponse.created_at.desc())
                        .limit(1)
                    )

                    resp = db.scalar(stmt)
                    cost = compute_response_cost(resp)
                    result["extraction_usd_spent"] += cost 
                    result["items_extracted"] += 1
            # SessionLocal.__exit__ calls close(), not commit(). Flush alone doesn't
            # persist — explicit commit required or ExtractorResponse rows are lost.
            db.commit()

    except BudgetExceeded as exc:
        exc.partial_result = result 
        raise 

    except Exception as e:
        result["error"] = str(e)

    finally:
        result["completed_at"] = datetime.datetime.now(datetime.UTC).isoformat()
        logging.info(json.dumps({
            "kind": "recurring_scrape_digest",
            "niche": result["niche_name"],
            "items_scraped": result["items_scraped"],
            "items_inserted": result["items_inserted"],
            "items_updated": result["items_updated"],
            "items_extracted": result["items_extracted"],
            "items_cache_hit": result["items_cache_hit"],
            "extraction_usd_spent": result["extraction_usd_spent"],
            "elapsed_seconds": round(time.perf_counter() - start_time, 2),
            "ts": result["completed_at"],
            }))

    return result

