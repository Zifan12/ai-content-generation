
import uuid
import pytest
import statistics
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
import src.miner.storage  # noqa: F401 — registers MinerRanking with Base
import src.models.trend    # noqa: F401 — registers RawContentItem + DetectedTrend
import src.models.niche    # noqa: F401 — registers Niche
import src.models.blueprint  # noqa: F401 — registers BlueprintRecord

from src.models.trend import RawContentItem
from src.models.niche import Niche
from src.models.blueprint import BlueprintRecord
from src.miner.schemas import BlueprintCandidate, MinerEvidence
from src.miner.rank import rank_candidates


def make_item(db, niche, views, published_at, hook_type, pacing, audio_type, primary_emotion, loop_type):
    item = RawContentItem(
        platform="tiktok",
        platform_content_id=str(uuid.uuid4()),
        niche_id=niche.id,
        views=views,
        published_at=published_at,
        url="https://test.com",
    )
    db.add(item)
    db.flush()  # assigns item.id before BlueprintRecord needs it

    blueprint = BlueprintRecord(
        content_item_id=item.id,
        extractor_version="v3.1",
        extractor_model="test",
        blueprint_data={
            "hook_type": hook_type,
            "pacing": pacing,
            "audio_type": audio_type,
            "primary_emotion": primary_emotion,
            "loop_type": loop_type,
            "aesthetic_descriptors": ["cinematic", "dark"],
            "niche_label": niche.name,
            "color_mood": "vivid_saturated",
            "visual_complexity": "moderate",
            "share_hook_type": "technical_awe",
            "comment_bait_type": "open_ending",
            "duration_band": "20_40s",
            "extractor_version": "v3.1",
            "extractor_model": "test",
        },
    )
    db.add(blueprint)
    db.flush()

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()
    engine.dispose()

@pytest.fixture
def corpus(db):
    niche = Niche(
        name="surreal_hyperreal",
        keywords=[],
        hashtag_seeds=[]
    )

    db.add(niche)
    db.flush()

    for i in range(10):
        make_item(
            db=db,
            niche=niche,
            views=100_000 + i * 1000,
            published_at=datetime.now(timezone.utc),
            hook_type="curiosity_gap",
            pacing="fast",
            audio_type="trending_audio",
            primary_emotion="awe",
            loop_type="hard_cut",
        )


    for i in range(20):
        make_item(
            db=db,
            niche=niche,
            views=5_000 + i * 100,
            published_at=datetime.now(timezone.utc),
            hook_type="nostalgia_trigger",
            pacing="slow_atmospheric",
            audio_type="music_only",
            primary_emotion="humor",
            loop_type="none",
        )

    db.commit()
    return niche


def test_top_n_cap(db, corpus):
    result = rank_candidates(db, niche_label=corpus.name, top_n=5)
    assert len(result) <= 5


def test_stability(db, corpus):
    result1 = rank_candidates(db, niche_label=corpus.name, top_n=5)
    result2 = rank_candidates(db, niche_label=corpus.name, top_n=5)

    assert [c.rank for c in result1] == [c.rank for c in result2]


def test_discrimination(db, corpus):
    result = rank_candidates(db, niche_label=corpus.name, top_n=5)
    views = db.query(RawContentItem.views).filter(RawContentItem.niche_id == corpus.id).all()
    
    median = statistics.median([v[0] for v in views])
    assert result[0].evidence.median_views >= 3 * median

def test_recency_window(db, corpus):

    for i in range(5):
        make_item(
            db=db,
            niche=corpus,
            views=30_000 + i * 100,
            published_at=datetime.now(timezone.utc) - timedelta(weeks=10),
            hook_type="identity_signal",
            pacing="slow_atmospheric",
            audio_type="music_only",
            primary_emotion="tension",
            loop_type="seamless_visual",
        )

    db.commit()
    result = rank_candidates(db, niche_label=corpus.name, top_n=5, recency_weeks=4) 
    assert all(c.blueprint_template.get("hook_type", None) != "identity_signal" for c in result)

def test_min_combo_size(db, corpus):

    result = rank_candidates(db, niche_label=corpus.name, top_n=5, min_matching_items=31)

    assert result == []