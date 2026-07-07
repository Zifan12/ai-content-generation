from src.monitor.mode_playbook import load_mode_playbook
from src.monitor.schemas import (
    GapAnalysis,
    StoryCraftVerdict,
    StoryPitch,
    TrendingEvent,
)
from src.monitor.story_craft_gate import STORY_CRAFT_SYSTEM_PROMPT, StoryCraftGate
from tests.monitor.fixtures.bad_tableau_pitch import BAD_TABLEAU_PITCH

# --- ingredients evaluate() needs: an event, a gap, and a canned verdict ------

SAMPLE_EVENT = TrendingEvent(
    headline="Dragon spotted circling Tokyo Tower at dawn",
    subreddit="interestingasfuck",
    url="https://reddit.com/r/interestingasfuck/comments/abc123",
    reaction_sample="Top comment: 'I wish we got to see it actually breathe fire.' "
    "Reply: 'They cut away right before the good part, classic.'",
    trendiness_score=0.92,
    virality_window_hours=18.0,
    raw_source_data={},
    origin="scraped",
)


def _sample_gap() -> GapAnalysis:
    return GapAnalysis(
        dominant_emotion="longing",
        audience_want="to see the dragon actually breathe fire",
        evidence_quotes=["I wish we got to see it actually breathe fire."],
        virality_window_hours=18.0,
        reasoning="The crowd was teased a payoff the footage never delivered.",
    )


def _verdict(
    *,
    clear_desire: bool = True,
    visible_turn: bool = True,
    earned_payoff: bool = True,
    emotion_physical_tell: bool = True,
    cold_viewer_legible: bool = True,
    kinetic_payoff: bool = True,
    register_match: bool = True,
    dialogue_earns_place: bool = True,
    scene_setting_contained: bool = True,
    would_watch: bool = True,
) -> StoryCraftVerdict:
    """Build a verdict with all nine craft dims + would_watch set as asked.

    Note we NEVER pass ``passes`` — it is a computed property on the schema,
    derived from these ten booleans.  Whatever these are set to, ``passes``
    follows automatically.  That is the exact behaviour the pass/fail tests
    below pin down.
    """
    return StoryCraftVerdict(
        clear_desire=clear_desire,
        visible_turn=visible_turn,
        earned_payoff=earned_payoff,
        emotion_physical_tell=emotion_physical_tell,
        cold_viewer_legible=cold_viewer_legible,
        kinetic_payoff=kinetic_payoff,
        register_match=register_match,
        dialogue_earns_place=dialogue_earns_place,
        scene_setting_contained=scene_setting_contained,
        notes="canned verdict for testing",
        failure_notes=None,
        would_watch=would_watch,
    )


class FakeLLM:
    """Stand-in for AnthropicLLM: returns a verdict we choose, records the prompt.

    No network, no cost, deterministic — so any variation in the gate's output
    is the gate's own behaviour, never the LLM's randomness.
    """

    def __init__(self, verdict: StoryCraftVerdict) -> None:
        self._verdict = verdict

    def parse(self, prompt: str, response_model: type, **kwargs) -> StoryCraftVerdict:
        self.prompt = prompt  # remember what the gate handed us, to assert on
        return self._verdict


# --- the tests ----------------------------------------------------------------


def test_all_dims_true_passes():
    """All four craft dims true + would_watch true -> passes is True."""
    fake = FakeLLM(_verdict())  # every dim defaults to True
    gate = StoryCraftGate(llm=fake)

    result = gate.evaluate(BAD_TABLEAU_PITCH, SAMPLE_EVENT, _sample_gap())

    assert result.passes is True


def test_one_dim_false_fails():
    """Flip a single dim to false -> passes must be False.

    This is the discrimination check: the pass logic actually distinguishes a
    good verdict from a bad one (the anti-"everything scores 5.00" guard).
    """
    fake = FakeLLM(_verdict(visible_turn=False))
    gate = StoryCraftGate(llm=fake)

    result = gate.evaluate(BAD_TABLEAU_PITCH, SAMPLE_EVENT, _sample_gap())

    assert result.passes is False


def test_prompt_carries_pitch_mode_emphasis_and_satire_wording():
    """The gate injects the PITCH's own mode craft_emphasis into the prompt, and
    the judge system prompt carries the satire 'landed contrast' branch."""
    fake = FakeLLM(_verdict())
    gate = StoryCraftGate(llm=fake)

    gate.evaluate(BAD_TABLEAU_PITCH, SAMPLE_EVENT, _sample_gap())

    # BAD_TABLEAU_PITCH.mode == wish, so the wish emphasis must be in the prompt.
    wish_emphasis = load_mode_playbook()["wish"].craft_emphasis
    assert wish_emphasis in fake.prompt
    # The satire branch lives in the constant judge prompt.
    assert "CONTRAST must LAND IN A SINGLE VISUAL" in STORY_CRAFT_SYSTEM_PROMPT


def test_bad_tableau_fixture_still_validates():
    """Rot guard: the negative-control fixture must remain a schema-valid
    StoryPitch, so any future schema change that breaks it fails loudly here."""
    assert isinstance(BAD_TABLEAU_PITCH, StoryPitch)
    assert len(BAD_TABLEAU_PITCH.beats) == 3


def test_prompt_carries_all_nine_dimensions():
    for label in (
        "clear_desire",
        "visible_turn",
        "earned_payoff",
        "emotion_physical_tell",
        "cold_viewer_legible",
        "kinetic_payoff",
        "register_match",
        "dialogue_earns_place",
        "scene_setting_contained",
    ):
        assert label in STORY_CRAFT_SYSTEM_PROMPT


def test_dialogue_earns_place_auto_yes_when_no_dialogue_documented():
    assert "automatically" in STORY_CRAFT_SYSTEM_PROMPT


def test_new_dim_false_fails():
    """Any one of the 5 new dims flipped false must fail passes (Task 1's
    computed passes), proving the gate's verdict construction plumbs them
    through end to end."""
    fake = FakeLLM(_verdict(cold_viewer_legible=False))
    gate = StoryCraftGate(llm=fake)

    result = gate.evaluate(BAD_TABLEAU_PITCH, SAMPLE_EVENT, _sample_gap())

    assert result.passes is False
