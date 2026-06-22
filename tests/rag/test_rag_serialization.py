from src.rag.serialization import (
    serialize_for_embed,
    serialize_candidate_for_query,
    embed_text_hash,
)
from src.miner.schemas import BlueprintCandidate, MinerEvidence


def _full_blueprint() -> dict:
    """Reusable Blueprint dict with all 6 embed-relevant fields populated."""
    return {
        "aesthetic_descriptors": ["liminal_space", "uncanny_realism"],
        "hook_type": "visual_shock",
        "hook_subtype": "jump_scare",
        "primary_emotion": "awe",
        "pacing": "fast",
        "audio_type": "trending_audio",
        "color_mood": "neon",
    }


def _candidate(blueprint_template: dict) -> BlueprintCandidate:
    """Build minimal valid BlueprintCandidate for query-side tests."""
    return BlueprintCandidate(
        rank=1,
        niche_label="surreal_hyperreal",
        blueprint_template=blueprint_template,
        evidence=MinerEvidence(
            matching_items=1,
            median_views=1000,
            p90_views=5000,
            trend_slope_4wk_pct=0.1,
            rationale="test fixture",
        ),
    )

def test_round_trip_all_fields():
    blueprint_data = {
        "aesthetic_descriptors": ["liminal_space", "uncanny_realism"],
        "hook_type": "visual_shock",
        "hook_subtype": "jump_scare",
        "primary_emotion": "awe",
        "pacing": "fast",
        "audio_type": "trending_audio",
        "color_mood": "neon",
    }
    actual = serialize_for_embed(
        description="sample caption",
        hashtags=["viral", "fyp", "tiktok"],
        transcript="hello world",
        blueprint_data=blueprint_data,
    )
    expected = "\n".join([
        "description: sample caption",
        "hashtags: viral fyp tiktok",
        "transcript: hello world",
        "aesthetic: liminal_space, uncanny_realism",
        "hook: visual_shock / jump_scare",
        "emotion: awe",
        "pacing: fast",
        "audio: trending_audio",
        "mood: neon",
    ])
    assert actual == expected


def test_missing_transcript_skips_line():
    actual = serialize_for_embed(
        description="sample caption",
        hashtags=["viral", "fyp"],
        transcript=None,
        blueprint_data=_full_blueprint(),
    )
    assert "transcript:" not in actual
    assert "description: sample caption" in actual
    assert "hashtags: viral fyp" in actual
    assert "hook: visual_shock / jump_scare" in actual


def test_empty_aesthetic_skips_line():
    blueprint_data = _full_blueprint()
    blueprint_data["aesthetic_descriptors"] = []
    actual = serialize_for_embed(
        description="sample caption",
        hashtags=["viral"],
        transcript="hello",
        blueprint_data=blueprint_data,
    )
    assert "aesthetic:" not in actual
    assert "hook: visual_shock / jump_scare" in actual
    assert "emotion: awe" in actual
    assert "mood: neon" in actual


def test_hash_determinism():
    text = "description: sample\nhook: visual_shock"
    assert embed_text_hash(text) == embed_text_hash(text)
    assert embed_text_hash(text) != embed_text_hash(text + " ")
    assert len(embed_text_hash(text)) == 16


def test_parity_index_vs_query():
    bp = _full_blueprint()
    index_side = serialize_for_embed(
        description=None,
        hashtags=None,
        transcript=None,
        blueprint_data=bp,
    )
    query_side = serialize_candidate_for_query(_candidate(bp))
    assert index_side == query_side
