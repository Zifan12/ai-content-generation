import pytest
from pydantic import ValidationError
from src.monitor.schemas import (
    BriefField,
    BriefFieldDraft,
    Camp,
    EvidenceQuote,
    FactionMap,
    FactionMapDraft,
    GapAnalysis,
    PlanDecision,
    TopicBrief,
    TopicBriefDraft,
)


def test_GapAnalysis():
    gap = GapAnalysis(
        dominant_emotion="anger",
        audience_want="the violent climax they never got",
        evidence_quotes=["they cut away right before the good part"],
        reasoning="audience explicitly asked for this in comments",
    )
    assert gap.evidence_quotes == ["they cut away right before the good part"]
    assert gap.dominant_emotion == "anger"


def test_evidence_quotes_default_empty():
    # evidence_quotes is optional and defaults to an empty list.
    gap = GapAnalysis(
        dominant_emotion="anger",
        audience_want="the violent climax they never got",
        reasoning="audience explicitly asked for this in comments",
    )
    assert gap.evidence_quotes == []


def test_too_many_evidence_quotes_rejected():
    # the schema caps evidence_quotes at 3; a 4th must fail validation.
    with pytest.raises(ValidationError):
        GapAnalysis(
            dominant_emotion="anger",
            audience_want="the violent climax they never got",
            evidence_quotes=["a", "b", "c", "d"],
            reasoning="audience explicitly asked for this in comments",
        )


def test_extra_field_DNE():
    with pytest.raises(ValidationError):
        GapAnalysis(
            dominant_emotion="anger",
            audience_want="the violent climax they never got",
            reasoning="audience explicitly asked for this in comments",
            mood="cheerful",
        )


def test_plan_decision_next_url_defaults_empty():
    decision = PlanDecision(next_action="reddit_search", next_query="some query")
    assert decision.next_url == ""


def test_plan_decision_accepts_firecrawl_extract_action():
    decision = PlanDecision(
        next_action="firecrawl_extract",
        next_query="",
        next_url="https://example.com/wiki/X",
    )
    assert decision.next_action == "firecrawl_extract"
    assert decision.next_url == "https://example.com/wiki/X"


def _verified_field(text: str) -> BriefField:
    return BriefField(content=text, citations=["https://example.com/source"])


def test_topic_brief_constructs_with_all_five_fields_verified():
    brief = TopicBrief(
        identity=_verified_field("A gacha RPG about exiled spirits"),
        recent_events=_verified_field("Season 2 finale aired last week"),
        key_characters=_verified_field("Albis and Serfort, bonded rivals"),
        why_people_care=_verified_field("Fans wanted the reunion scene"),
        open_unknowns=["whether a season 3 has been greenlit"],
    )
    assert brief.identity.content == "A gacha RPG about exiled spirits"
    # content and citations are separately inspectable, never concatenated
    assert brief.identity.citations == ["https://example.com/source"]
    assert brief.open_unknowns == ["whether a season 3 has been greenlit"]


def test_topic_brief_rejects_extra_fields():
    with pytest.raises(ValidationError):
        TopicBrief(
            identity=_verified_field("x"),
            recent_events=_verified_field("x"),
            key_characters=_verified_field("x"),
            why_people_care=_verified_field("x"),
            open_unknowns=[],
            wave_status="hot",  # no such field — explicitly out of scope
        )


def test_brief_field_defaults_verified_true():
    field = BriefField(content="fact", citations=["https://example.com/a"])
    assert field.verified is True


def test_one_field_unverified_others_verified_is_a_valid_brief():
    # the checker-exhaustion path (ticket 03/04) stamps individual failing
    # fields UNVERIFIED without discarding the other four fields' citations.
    brief = TopicBrief(
        identity=_verified_field("A gacha RPG about exiled spirits"),
        recent_events=BriefField(content="unclear", citations=[], verified=False),
        key_characters=_verified_field("Albis and Serfort, bonded rivals"),
        why_people_care=_verified_field("Fans wanted the reunion scene"),
        open_unknowns=[],
    )
    assert brief.recent_events.verified is False


def _camp(name: str) -> Camp:
    return Camp(
        name=name,
        feeling="hopeful",
        surface_want="wants a reunion on screen",
        deeper_desire="wants proof the years apart still mattered",
        evidence_quotes=[EvidenceQuote(quote="please just let them reunite", upvotes=80)],
        weight=1.0,
    )


def test_faction_map_rejects_empty_camps():
    # FIX 7: an empty map would let ideation's per-camp coverage check pass
    # vacuously (zero camps to cover) -- min_length=1 forbids it outright.
    with pytest.raises(ValidationError):
        FactionMap(camps=[])


def test_faction_map_single_camp_is_valid():
    faction_map = FactionMap(camps=[_camp("solo")])
    assert len(faction_map.camps) == 1


def test_faction_map_draft_allows_empty_camps():
    # The LLM-facing draft is deliberately unconstrained -- an empty draft is
    # the READER's signal to retry (FactionReader.read), not a shape this
    # schema itself should forbid.
    draft = FactionMapDraft(camps=[])
    assert draft.camps == []


def test_brief_field_citation_is_url_identifiable():
    field = _verified_field("fact")
    assert field.citations[0].startswith("https://")


def test_topic_brief_draft_has_no_verified_flag():
    draft = TopicBriefDraft(
        identity=BriefFieldDraft(content="x", citations=["https://example.com/a"]),
        recent_events=BriefFieldDraft(content="x", citations=["https://example.com/a"]),
        key_characters=BriefFieldDraft(content="x", citations=["https://example.com/a"]),
        why_people_care=BriefFieldDraft(content="x", citations=["https://example.com/a"]),
        open_unknowns=["some gap"],
    )
    with pytest.raises(ValidationError):
        # a draft field constructed with a verified flag must fail — the LLM
        # never emits it, only the checker-composed BriefField carries one.
        BriefFieldDraft(content="x", citations=[], verified=True)
    assert draft.open_unknowns == ["some gap"]
