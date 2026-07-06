from src.reference.schemas import VideoCandidate
from src.reference.video_finder import shortlist

IP_SOURCE = "Stellar Blade"


def _candidate(**overrides: object) -> VideoCandidate:
    defaults = {
        "video_id": "abc123",
        "url": "https://youtube.com/watch?v=abc123",
        "title": "Stellar Blade Eve Official Trailer",
        "channel": "PlayStation",
        "duration_seconds": 90.0,
        "view_count": 1000,
        "description": "",
        "transcript_excerpt": None,
    }
    defaults.update(overrides)
    return VideoCandidate(**defaults)


def test_empty_input_returns_empty_list():
    assert shortlist([], ip_source=IP_SOURCE, max_duration_seconds=900, shortlist_size=5) == []


def test_drops_over_cap_duration_candidates():
    short = _candidate(video_id="a", duration_seconds=90.0)
    over_cap = _candidate(video_id="b", duration_seconds=1000.0)

    result = shortlist(
        [short, over_cap], ip_source=IP_SOURCE, max_duration_seconds=900, shortlist_size=5
    )

    assert result == [short]


def test_duration_exactly_at_cap_is_kept():
    at_cap = _candidate(video_id="a", duration_seconds=900.0)

    result = shortlist(
        [at_cap], ip_source=IP_SOURCE, max_duration_seconds=900, shortlist_size=5
    )

    assert result == [at_cap]


def test_dedupes_same_video_id_keeping_first_occurrence():
    first = _candidate(video_id="dup", view_count=100)
    second = _candidate(video_id="dup", view_count=999)
    other = _candidate(video_id="other", view_count=1)

    result = shortlist(
        [first, second, other], ip_source=IP_SOURCE, max_duration_seconds=900, shortlist_size=5
    )

    assert len(result) == 2
    assert result[0].view_count == 100  # first occurrence kept, not the higher-view duplicate
    assert any(c.video_id == "other" for c in result)


def test_title_match_outranks_non_match_regardless_of_view_count():
    matching = _candidate(
        video_id="a", title="Stellar Blade Eve Official Trailer", view_count=500
    )
    non_matching_high_views = _candidate(
        video_id="b", title="Random Reaction Video", view_count=1_000_000
    )

    result = shortlist(
        [non_matching_high_views, matching],
        ip_source=IP_SOURCE,
        max_duration_seconds=900,
        shortlist_size=5,
    )

    assert result[0].video_id == "a"


def test_title_match_is_case_insensitive():
    matching = _candidate(video_id="a", title="stellar blade eve trailer", view_count=1)
    non_matching = _candidate(video_id="b", title="unrelated video", view_count=1_000_000)

    result = shortlist(
        [non_matching, matching],
        ip_source=IP_SOURCE,
        max_duration_seconds=900,
        shortlist_size=5,
    )

    assert result[0].video_id == "a"


def test_view_count_breaks_ties_within_same_match_tier():
    low = _candidate(video_id="low", title="Stellar Blade Eve", view_count=10)
    high = _candidate(video_id="high", title="Stellar Blade Eve", view_count=999)

    result = shortlist(
        [low, high], ip_source=IP_SOURCE, max_duration_seconds=900, shortlist_size=5
    )

    assert result[0].video_id == "high"
    assert result[1].video_id == "low"


def test_none_view_count_treated_as_zero():
    unknown = _candidate(video_id="unknown", title="Stellar Blade Eve", view_count=None)
    known = _candidate(video_id="known", title="Stellar Blade Eve", view_count=1)

    result = shortlist(
        [unknown, known], ip_source=IP_SOURCE, max_duration_seconds=900, shortlist_size=5
    )

    assert result[0].video_id == "known"
    assert result[1].video_id == "unknown"


def test_truncates_to_shortlist_size():
    candidates = [
        _candidate(video_id=str(i), title="Stellar Blade Eve", view_count=i) for i in range(10)
    ]

    result = shortlist(
        candidates, ip_source=IP_SOURCE, max_duration_seconds=900, shortlist_size=3
    )

    assert len(result) == 3
    assert [c.video_id for c in result] == ["9", "8", "7"]
