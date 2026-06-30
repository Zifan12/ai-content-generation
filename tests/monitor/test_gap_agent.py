from src.monitor.gap_agent import GapAgent
from src.monitor.schemas import GapAnalysis, GapType, TrendingEvent

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

class FakeLLM:
    def __init__(self, analysis: GapAnalysis) -> None:
        self._analysis = analysis
       

    def parse(self, prompt: str, response_model: type, **kwargs) -> GapAnalysis:
        self.prompt = prompt
        return self._analysis


def test_analysis():
    analysis = GapAnalysis(
        dominant_emotion="longing",
        audience_want="to see the dragon actually breathe fire",
        gap_type=GapType.alternate_reality,
        producibility_score=0.8,
        virality_window_hours=18.0,
        reasoning="The crowd was teased a payoff the footage never delivered.",
    )

    fake = FakeLLM(analysis=analysis)
    agent = GapAgent(llm=fake)
    result = agent.analyze(SAMPLE_EVENT)

    assert result == analysis
    assert "Dragon spotted circling Tokyo Tower" in fake.prompt
    
