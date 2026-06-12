
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pydantic import ValidationError

from src.database import Base
import src.models.trend       # noqa: F401 — registers RawContentItem with Base.metadata
import src.models.transcript  # noqa: F401 — registers Transcript with Base.metadata
import src.models.niche       # noqa: F401 — registers Niche (FK target of RawContentItem)

from src.schemas.generation import ContentPackage, Shot
from src.miner.schemas import MinerEvidence
from src.miner.schemas import BlueprintCandidate
from src.models.trend import RawContentItem
from src.models.transcript import Transcript
from src.rag.schemas import RetrievalHit
from src.generation.content_writer import build_envelope, _hydrate_hits, ContentWriter

# A valid 3-segment chain for tests that just need a schema-valid ContentPackage.
# Chain shape (design §4): ONLY segment 1 carries start_keyframe (the one generated
# opening still); segments 2-3 inherit their start frame from the previous clip's last
# frame, so start_keyframe is None there (and the chain-contract validator REQUIRES it
# to be). mood_anchor is now package-level, not per-shot. Every segment has `motion`;
# end_keyframe stays optional (set when the segment must reach a specific visual state).
VALID_SHOTS = [
    Shot(start_keyframe="wide shot, harbor at dawn", motion="slow push in"),
    Shot(motion="tentacle sweeps up and grabs", end_keyframe="kraken grips the ship"),
    Shot(motion="crowd scatters off the dock", end_keyframe="dock emptied, ship dragged under"),
]

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    yield session   
    session.close()
    engine.dispose()

def test_content_package_validates_minimal():
    package = ContentPackage(
        shots=VALID_SHOTS,
        onscreen_text=["test", "test", "test"],
        caption="test123",
        hashtags=["test1", "test2"],
        device="wrongness_creep",
        device_rationale="test rationale",
        mood_anchor="cold teal, photoreal",
    )

    assert package.grounding_hit_ids == []
    assert package.voiceover is None
    assert package.rationale is None

def test_content_package_rejects_missing_shots():
    with pytest.raises(ValidationError):
        ContentPackage(
        onscreen_text=["test", "test", "test"],
        caption="test123",
        hashtags=["test1", "test2"],
        device="wrongness_creep",
        device_rationale="test rationale",
        mood_anchor="cold teal, photoreal",
    )

def test_content_package_rejects_wrong_shot_count():
    # exactly-3 is enforced at the schema level (Field min_length=max_length=3),
    # not left to the prompt. Two shots must be rejected just like zero.
    with pytest.raises(ValidationError):
        ContentPackage(
            shots=VALID_SHOTS[:2],
            onscreen_text=["test"],
            caption="test123",
            hashtags=["test1"],
            device="wrongness_creep",
            device_rationale="test rationale",
            mood_anchor="cold teal, photoreal",
        )


def test_content_package_accepts_valid_device():
    # A valid closed-menu device + a rationale must validate. Pins the happy path
    # for the creative-device field (replaces organizing_principle).
    package = ContentPackage(
        shots=VALID_SHOTS,
        onscreen_text=["test"],
        caption="test123",
        hashtags=["test1"],
        device="scale_traversal",
        device_rationale="premise is one colossal subject, so travel past it.",
        mood_anchor="cold teal, photoreal",
    )
    assert package.device == "scale_traversal"


def test_content_package_rejects_invalid_device():
    # The menu is CLOSED — an off-menu value (here a retired vignette principle)
    # must raise, which is what makes cross-run monotony detectable via
    # device_distribution + the field evalable.
    with pytest.raises(ValidationError):
        ContentPackage(
            shots=VALID_SHOTS,
            onscreen_text=["test"],
            caption="test123",
            hashtags=["test1"],
            device="sustained_mood",
            device_rationale="test rationale",
            mood_anchor="cold teal, photoreal",
        )


def test_content_package_requires_device_rationale():
    # device_rationale is REQUIRED (no default) — the writer must justify the pick,
    # not silently default to a habit. Omitting it must raise.
    with pytest.raises(ValidationError):
        ContentPackage(
            shots=VALID_SHOTS,
            onscreen_text=["test"],
            caption="test123",
            hashtags=["test1"],
            device="wrongness_creep",
            mood_anchor="cold teal, photoreal",
        )


def test_content_package_requires_mood_anchor():
    # mood_anchor moved up to package level (one grade for the continuous take) and
    # is REQUIRED — the take has no grade-lock without it. Omitting it must raise.
    with pytest.raises(ValidationError):
        ContentPackage(
            shots=VALID_SHOTS,
            onscreen_text=["test"],
            caption="test123",
            hashtags=["test1"],
            device="wrongness_creep",
            device_rationale="test rationale",
        )


def test_shot_no_motion():
    # motion is required (every segment moves). Everything else is optional now, so
    # an empty Shot() must raise solely on the absent motion.
    with pytest.raises(ValidationError):
        Shot()


def test_shot_start_keyframe_optional():
    # start_keyframe is now OPTIONAL on Shot itself (segments 2-3 inherit their start
    # frame). A motion-only Shot must construct and default start_keyframe to None.
    # The opener-requires-it rule lives at the PACKAGE level (chain-contract
    # validator), not on Shot — see test_content_package_rejects_opener_without_start_keyframe.
    shot = Shot(motion="slow push in")
    assert shot.start_keyframe is None


def test_shot_end_keyframe_optional():
    # end_keyframe is the idle-vs-event switch: omitting it must SUCCEED (a segment
    # with no end-state to reach) and default to None.
    shot = Shot(start_keyframe="wide shot, harbor at dawn", motion="slow push in")
    assert shot.end_keyframe is None


# --- NET-NEW: chain-contract validator tests (NOT a rename — new behavior in
# ContentPackage._check_chain_contract). These pin the two structural invariants the
# field types alone cannot express. If you want the TDD rep, rewrite these yourself.

def _shots_with(start_keyframes):
    # Build 3 shots from a list of 3 start_keyframe values (None = inheritor). motion
    # is always present so the ONLY thing under test is the start_keyframe placement.
    return [Shot(start_keyframe=sk, motion="some move") for sk in start_keyframes]


def test_content_package_rejects_opener_without_start_keyframe():
    # Segment 1 with no start_keyframe = nothing to render the opening still from.
    # The validator must reject even though each Shot is individually valid.
    with pytest.raises(ValidationError):
        ContentPackage(
            shots=_shots_with([None, None, None]),
            onscreen_text=["test"],
            caption="test123",
            hashtags=["test1"],
            device="wrongness_creep",
            device_rationale="test rationale",
            mood_anchor="cold teal, photoreal",
        )


def test_content_package_rejects_inheritor_with_start_keyframe():
    # An inheriting segment (2 or 3) that carries its own start_keyframe = the writer
    # re-rolled the world mid-chain, breaking continuity. Must reject.
    with pytest.raises(ValidationError):
        ContentPackage(
            shots=_shots_with(["opening still", "smuggled re-roll", None]),
            onscreen_text=["test"],
            caption="test123",
            hashtags=["test1"],
            device="wrongness_creep",
            device_rationale="test rationale",
            mood_anchor="cold teal, photoreal",
        )


def test_build_envelope_includes_target_and_winners():
    evidence = MinerEvidence(
        matching_items=1,
        median_views=0,
        p90_views=0,
        trend_slope_4wk_pct=0.0,
        rationale="test"
    )

    candidate = BlueprintCandidate(
        rank=1,
        niche_label="surreal_hyperreal",
        blueprint_template={"niche_label": "ITS2AMINTHEMORNING"},
        evidence=evidence,
        
    )

    # hydrated_hits now carry transcript (None when absent) + blueprint-derived
    # aesthetic_descriptors / hook_subtype. Hit 2 has NO transcript, so it must
    # still contribute its aesthetics — that proves the floor-signal fix.
    hits = [
        {
            "transcript": "SPOKEN_AAA",
            "aesthetic_descriptors": ["dreamcore_void", "uncanny_AAA"],
            "hook_subtype": "impossible_visual",
        },
        {
            "transcript": None,
            "aesthetic_descriptors": ["liminal_BBB"],
            "hook_subtype": "slow_reveal",
        },
    ]

    premise = "JUNKER"

    result = build_envelope(candidate, hits, premise)

    assert "ITS2AMINTHEMORNING" in result          # target template present
    assert "uncanny_AAA" in result                 # hit 1 aesthetics
    assert "liminal_BBB" in result                 # hit 2 aesthetics (no transcript, still included)
    assert "SPOKEN_AAA" in result                  # hit 1 transcript present
    assert "impossible_visual" in result           # hit 1 hook subtype
    assert "Example 1" in result and "Example 2" in result  # per-winner labels
    assert "CAPTION" not in result                 # captions are no longer grounded
    assert "JUNKER" in result


def test_hydrate_pulls_transcript_and_blueprint_fields(db):
    item1 = RawContentItem(
        platform="tiktok",
        platform_content_id="vid1",
        url="https://test.com/1",
        description="CAPTION_ONE",
    )
    item2 = RawContentItem(
        platform="tiktok",
        platform_content_id="vid2",
        url="https://test.com/2",
        description="CAPTION_TWO",
    )

    db.add(item1)
    db.add(item2)
    db.flush()  # assigns item1.id / item2.id before the Transcript FK + hits need them

    # Transcript linked to item1 only. item2 deliberately has none, so the
    # outerjoin must keep item2's hit and report its transcript as None (not a
    # placeholder string — absence is carried truthfully, the formatter decides
    # how to render it).
    has_transcript = Transcript(
        content_item_id=item1.id,
        text="TRANSCRIPT_ONE",
        source="test",
    )
    db.add(has_transcript)
    db.flush()

    # aesthetic_descriptors + hook_subtype are read off the hit's blueprint_data
    # (no DB round-trip). hit1 carries them; hit2's empty blueprint_data exercises
    # the missing path (-> None).
    hit1 = RetrievalHit(
        content_item_id=item1.id,
        blueprint_id=1,
        score=0.9,
        blueprint_data={
            "aesthetic_descriptors": ["dreamcore_void", "uncanny_AAA"],
            "hook_subtype": "impossible_visual",
        },
        niche_label="surreal_hyperreal",
    )
    hit2 = RetrievalHit(
        content_item_id=item2.id,
        blueprint_id=2,
        score=0.8,
        blueprint_data={},
        niche_label="surreal_hyperreal",
    )

    result = _hydrate_hits([hit1, hit2], db)

    # hit1: has transcript + populated blueprint fields
    assert result[0]["transcript"] == "TRANSCRIPT_ONE"
    assert result[0]["aesthetic_descriptors"] == ["dreamcore_void", "uncanny_AAA"]
    assert result[0]["hook_subtype"] == "impossible_visual"

    # hit2: no transcript -> None (not "(missing)"); empty blueprint -> None fields
    assert result[1]["transcript"] is None
    assert result[1]["aesthetic_descriptors"] is None
    assert result[1]["hook_subtype"] is None

    # caption is no longer hydrated at all
    assert "caption" not in result[0]

# ------------------------------------------------------------------

class FakeLLM():
     def parse(self, prompt, response_model, system=None, max_tokens=1024):
        package = ContentPackage(
        shots=VALID_SHOTS,
        onscreen_text=["test", "test", "test"],
        caption="test123",
        hashtags=["test1", "test2"],
        grounding_hit_ids=[],
        device="wrongness_creep",
        device_rationale="test rationale",
        mood_anchor="cold teal, photoreal",
        )

        return package
        


def test_write_returns_package_and_sets_grounding_ids(db):

    item1 = RawContentItem(
        platform="tiktok",
        platform_content_id="vid1",
        url="https://test.com/1",
        description="CAPTION_ONE",
    )
    item2 = RawContentItem(
        platform="tiktok",
        platform_content_id="vid2",
        url="https://test.com/2",
        description="CAPTION_TWO",
    )

    db.add(item1)
    db.add(item2)
    db.flush()  


    has_transcript = Transcript(
        content_item_id=item1.id,
        text="TRANSCRIPT_ONE",
        source="test",
    )
    db.add(has_transcript)
    db.flush()

    hit1 = RetrievalHit(
        content_item_id=item1.id,
        blueprint_id=1,
        score=0.9,
        blueprint_data={},
        niche_label="surreal_hyperreal",
    )
    hit2 = RetrievalHit(
        content_item_id=item2.id,
        blueprint_id=2,
        score=0.8,
        blueprint_data={},
        niche_label="surreal_hyperreal",
    )
    hits = [hit1, hit2]

    
    evidence = MinerEvidence(
        matching_items=1,
        median_views=0,
        p90_views=0,
        trend_slope_4wk_pct=0.0,
        rationale="test"
    )

    
    candidate = BlueprintCandidate(
        rank=1,
        niche_label="surreal_hyperreal",
        blueprint_template={"niche_label": "ITS2AMINTHEMORNING"},
        evidence=evidence,
        
    )

    premise = "JUNKER"

    writer = ContentWriter(llm=FakeLLM())

    result = writer.write(candidate, hits, db, premise)

    assert isinstance(result, ContentPackage)
    assert result.grounding_hit_ids == [h.content_item_id for h in hits]

def test_write_empty_hits_raises():

    evidence = MinerEvidence(
        matching_items=1,
        median_views=0,
        p90_views=0,
        trend_slope_4wk_pct=0.0,
        rationale="test"
    )
    candidate = BlueprintCandidate(
        rank=1,
        niche_label="surreal_hyperreal",
        blueprint_template={"niche_label": "ITS2AMINTHEMORNING"},
        evidence=evidence,
        
    )

    premise = ""
    
    writer = ContentWriter(llm=FakeLLM())
    with pytest.raises(ValueError):
        writer.write(candidate, [], None, premise)



