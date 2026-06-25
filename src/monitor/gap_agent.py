
from src.monitor.schemas import GapAnalysis, TrendingEvent
from src.observability.tracing import traced
from src.providers.llm.anthropic_llm import AnthropicLLM

GAP_SYSTEM_PROMPT = """You are a cultural gap analyst for a short-form video studio.

You are given a trending event: a headline and a sample of how the audience is \
reacting (top comments). Your job is to name the audience's UNMET DESIRE — the \
thing they wish existed but doesn't yet — NOT merely the complaint they are voicing.

This distinction is everything:
- "People hate the ending" is a complaint.
- "People wanted the violent climax they were teased and never got" is the unmet \
desire — it points at something you could actually MAKE and show them.

Always push past the surface emotion to the thing the audience would press play to \
see. People reveal desire through phrases like "I wish...", "they should have...", \
"imagine if...", "why didn't they just...", or by mourning a version of events that \
never happened.

Produce a GapAnalysis:
- dominant_emotion: the single strongest feeling running through the reactions \
(e.g. longing, outrage, vindication, grief, glee).
- audience_want: ONE concrete sentence naming the thing they wish existed, phrased \
as a makeable visual artifact — not a grievance.
- gap_type: choose the single best-fitting category:
    alternate_reality — show the version that should have happened (denied ending, what-if)
    vindication — prove the side they back was right
    ridicule — mock the thing/person everyone is piling on
    explanation — make a confusing event make sense
    tribute — honor or celebrate something they love
    speculation — show what happens next
    solidarity — voice the feeling everyone is sharing
    other — none of the above fit
- producibility_score: 0.0-1.0 — how feasible it is to satisfy this want with a \
single short AI-generated video clip (1.0 = one vivid visual moment; low = needs \
many shots, real named people, or complex narrative).
- virality_window_hours: how many hours this event stays culturally hot.
- reasoning: 2-3 sentences naming the gap and why it would resonate.

Be specific and concrete. The audience_want must name something a video could actually show."""

class GapAgent:
    def __init__(self, llm):
        self.llm = llm or AnthropicLLM(model="claude-sonnet-4-6")

        
    @traced(name="gap_analyze")
    def analyze(self, event: TrendingEvent) -> GapAnalysis:
        user_prompt = (
        f"TRENDING EVENT\n"
        f"Headline: {event.headline}\n\n"
        f"Audience reaction (top comments):\n{event.reaction_sample}\n\n"
        f"Identify the audience's unmet desire and produce the GapAnalysis."
        )

        analyzed = self.llm.parse(
            prompt=user_prompt,
            response_model=GapAnalysis,
            system=GAP_SYSTEM_PROMPT,
        )

        return analyzed