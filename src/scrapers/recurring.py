import datetime
import asyncio

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

class BudgetExceeded(Exception): 
    pass 

DEFAULT_MAX_DAILY_SPEND = 1.00

def _get_transcript_text(db, content_item_id) -> str | None:
    stmt = (
        select(Transcript.text)
        .where(Transcript.content_item_id == content_item_id)
    )
    return db.scalar(stmt)

def run_niche_scrape(niche_id: int, session_factory: Callable[[], Session] = SessionLocal) -> dict:

    started_at = datetime.datetime.now(datetime.UTC).isoformat()
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
            niche = db.query(Niche).filter(Niche.id == niche_id).first()
            if niche is None:
                raise ValueError(f"Niche id={niche_id} not found")
            result["niche_name"] = niche.name

            scraper = TikTokScraper(db)
            items = asyncio.run(
                scraper.fetch_trending(niche_id=niche_id, query=niche.hashtag_seeds, max_results=50)
            )
            result["items_scraped"] = len(items)
            result["items_inserted"] = len(items)   

            extractor = BlueprintExtractor()
            for item in items:
                transcript = _get_transcript_text(db, item.id)
                bp = extractor.reparse_from_cache(item, transcript, niche.name, db)

                if bp is not None:
                    result["items_cache_hit"] += 1
                else:
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

                    if result["extraction_usd_spent"] >= DEFAULT_MAX_DAILY_SPEND:
                        raise BudgetExceeded(f"Daily spend ${result['extraction_usd_spent']:.4f} exceeded ${DEFAULT_MAX_DAILY_SPEND:.2f}")
    except BudgetExceeded as exc:
        exc.partial_result = result 
        raise 

    except Exception as e:
        result["error"] = str(e)

    finally:
        result["completed_at"] = datetime.datetime.now(datetime.UTC).isoformat()

    return result

