import pytest
from pydantic import ValidationError

from src.monitor.schemas import ContextBundle, ContextSynthesis, PlanDecision, TrendingEvent
from src.monitor.tools import estimate_cost, reddit_search, tavily_search
from src.monitor.tools._types import ToolResult
import src.monitor.context_agent as context_agent_module
from src.monitor.context_agent import ContextAgent, build_context_bundle, decide_next_step, ContextAgentState


class FakePlanLLM:
    def __init__(self, decision: PlanDecision) -> None:
        self._decision = decision

    def parse(self, prompt: str, response_model: type, **kwargs) -> PlanDecision:
        self.prompt = prompt
        return self._decision


class FakeFinalizeLLM:
    def __init__(self, synthesis: ContextSynthesis) -> None:
        self._synthesis = synthesis

    def parse(self, prompt: str, response_model: type, **kwargs) -> ContextSynthesis:
        self.prompt = prompt
        return self._synthesis


class FakeSequenceLLM:
    """Drives ContextAgent.run() end-to-end: returns queued PlanDecisions in
    order for _plan's calls (dispatched by response_model), then a fixed
    ContextSynthesis for _finalize's single call.
    """

    def __init__(self, plan_decisions: list[PlanDecision], synthesis: ContextSynthesis) -> None:
        self._plan_decisions = list(plan_decisions)
        self._synthesis = synthesis

    def parse(self, prompt: str, response_model: type, **kwargs):
        if response_model is PlanDecision:
            return self._plan_decisions.pop(0)
        return self._synthesis


def test_decide_next_step():
    state = ContextAgentState(
        topic="",
        reddit_text="",
        tavily_text="",
        reddit_calls=3,
        tavily_calls=2,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="reddit_search",
        next_query="",
        urls=[],
        summary="",
        key_moments=[],
    )
    result = decide_next_step(state, max_tool_calls=5, max_run_apify_cost=2.00)

    assert result == "stop"


def test_decide_next_step_apify_cost_ceiling():
    """The cumulative Apify cost ceiling overrides everything, same as
    max_tool_calls — even when total_calls is well under the cap and the
    LLM wants to keep searching Reddit.
    """
    state = ContextAgentState(
        topic="",
        reddit_text="",
        tavily_text="",
        reddit_calls=1,
        tavily_calls=0,
        apify_cost_estimate=2.00,
        within_community="",
        next_action="reddit_search",
        next_query="",
        urls=[],
        summary="",
        key_moments=[],
    )
    result = decide_next_step(state, max_tool_calls=5, max_run_apify_cost=2.00)

    assert result == "stop"


def test_plan_returns_llm_decision():
    decision = PlanDecision(next_action="reddit_search", next_query="Wistoria season 2 finale")
    fake = FakePlanLLM(decision=decision)
    agent = ContextAgent(llm=fake)
    state = ContextAgentState(
        topic="Wistoria season 2 finale",
        reddit_text="",
        tavily_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="",
        next_query="",
        urls=[],
        summary="",
        key_moments=[],
    )

    result = agent._plan(state)

    assert result == {"next_action": "reddit_search", "next_query": "Wistoria season 2 finale"}
    assert "Wistoria season 2 finale" in fake.prompt


def test_finalize_returns_llm_synthesis():
    synthesis = ContextSynthesis(
        summary="Fans were furious the finale denied the long-teased reunion.",
        key_moments=["showrunner confirms no reunion planned"],
    )
    fake = FakeFinalizeLLM(synthesis=synthesis)
    agent = ContextAgent(llm=fake)
    state = ContextAgentState(
        topic="Wistoria season 2 finale",
        reddit_text="top comment: robbed",
        tavily_text="background: finale aired June 28",
        reddit_calls=1,
        tavily_calls=1,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="stop",
        next_query="",
        urls=[],
        summary="",
        key_moments=[],
    )

    result = agent._finalize(state)

    assert result == {
        "summary": "Fans were furious the finale denied the long-teased reunion.",
        "key_moments": ["showrunner confirms no reunion planned"],
    }
    assert "top comment: robbed" in fake.prompt
    assert "background: finale aired June 28" in fake.prompt


def test_act_reddit_appends_to_existing_text(monkeypatch):
    monkeypatch.setattr(
        context_agent_module,
        "reddit_search",
        lambda query, within_community=None: ToolResult(
            text="fresh reaction text", urls=["https://reddit.com/r/x/comments/1"]
        ),
    )
    agent = ContextAgent(llm=object())  # llm unused by _act_reddit
    state = ContextAgentState(
        topic="",
        reddit_text="earlier reaction text",
        tavily_text="",
        reddit_calls=1,
        tavily_calls=0,
        apify_cost_estimate=0.86,
        within_community="",
        next_action="reddit_search",
        next_query="some query",
        urls=["https://reddit.com/r/x/comments/0"],
        summary="",
        key_moments=[],
    )

    result = agent._act_reddit(state)

    assert result == {
        "reddit_text": "earlier reaction text\n\nfresh reaction text",
        "reddit_calls": 2,
        "apify_cost_estimate": 0.86 + estimate_cost(),
        "urls": ["https://reddit.com/r/x/comments/0", "https://reddit.com/r/x/comments/1"],
    }


def test_lookup_community_extracts_subreddit_from_url(monkeypatch):
    monkeypatch.setattr(
        context_agent_module,
        "tavily_search",
        lambda query: ToolResult(
            text="Wistoria is discussed on its subreddit.",
            urls=["https://www.reddit.com/r/Wistoria/", "https://example.com/wiki"],
        ),
    )
    agent = ContextAgent(llm=object())  # llm unused by _lookup_community
    state = ContextAgentState(
        topic="Wistoria",
        reddit_text="",
        tavily_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="",
        next_query="",
        urls=[],
        summary="",
        key_moments=[],
    )

    result = agent._lookup_community(state)

    assert result == {"within_community": "r/Wistoria"}


def test_lookup_community_empty_when_no_reddit_url(monkeypatch):
    monkeypatch.setattr(
        context_agent_module,
        "tavily_search",
        lambda query: ToolResult(text="no reddit link here", urls=["https://example.com/wiki"]),
    )
    agent = ContextAgent(llm=object())  # llm unused by _lookup_community
    state = ContextAgentState(
        topic="Wistoria",
        reddit_text="",
        tavily_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="",
        next_query="",
        urls=[],
        summary="",
        key_moments=[],
    )

    result = agent._lookup_community(state)

    assert result == {"within_community": ""}


def test_act_tavily_starts_fresh_when_empty(monkeypatch):
    monkeypatch.setattr(
        context_agent_module,
        "tavily_search",
        lambda query: ToolResult(text="background facts", urls=["https://example.com/article"]),
    )
    agent = ContextAgent(llm=object())  # llm unused by _act_tavily
    state = ContextAgentState(
        topic="",
        reddit_text="",
        tavily_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="tavily_search",
        next_query="some query",
        urls=[],
        summary="",
        key_moments=[],
    )

    result = agent._act_tavily(state)

    assert result == {
        "tavily_text": "background facts",
        "tavily_calls": 1,
        "urls": ["https://example.com/article"],
    }


def test_build_context_bundle_both_sources():
    state = ContextAgentState(
        topic="",
        reddit_text="top comment: robbed",
        tavily_text="background: finale aired June 28",
        reddit_calls=1,
        tavily_calls=1,
        apify_cost_estimate=0.86,
        within_community="",
        next_action="stop",
        next_query="",
        urls=["https://reddit.com/r/x/comments/1", "https://example.com/article"],
        summary="Fans were furious the finale denied the long-teased reunion.",
        key_moments=["showrunner confirms no reunion planned"],
    )

    bundle = build_context_bundle(state)

    assert bundle == ContextBundle(
        reaction_sample="top comment: robbed",
        summary="Fans were furious the finale denied the long-teased reunion.",
        key_moments=["showrunner confirms no reunion planned"],
        references=["https://reddit.com/r/x/comments/1", "https://example.com/article"],
        sources=["reddit_search", "tavily_search"],
        apify_cost_estimate=0.86,
    )


def test_build_context_bundle_no_sources():
    state = ContextAgentState(
        topic="",
        reddit_text="",
        tavily_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="stop",
        next_query="",
        urls=[],
        summary="",
        key_moments=[],
    )

    bundle = build_context_bundle(state)

    assert bundle.sources == []


def test_run_full_loop(monkeypatch):
    monkeypatch.setattr(
        context_agent_module,
        "reddit_search",
        lambda query, within_community=None: ToolResult(
            text="top comment: robbed", urls=["https://reddit.com/r/x/comments/1"]
        ),
    )
    monkeypatch.setattr(
        context_agent_module,
        "tavily_search",
        lambda query: ToolResult(text="background: finale aired June 28", urls=["https://example.com/article"]),
    )

    plan_decisions = [
        PlanDecision(next_action="reddit_search", next_query="finale reaction"),
        PlanDecision(next_action="tavily_search", next_query="finale background"),
        PlanDecision(next_action="stop", next_query=""),
    ]
    synthesis = ContextSynthesis(
        summary="Fans were furious the finale denied the long-teased reunion.",
        key_moments=["showrunner confirms no reunion planned"],
    )
    fake = FakeSequenceLLM(plan_decisions=plan_decisions, synthesis=synthesis)
    agent = ContextAgent(llm=fake, max_tool_calls=5)

    bundle = agent.run("Wistoria season 2 finale")

    assert bundle == ContextBundle(
        reaction_sample="top comment: robbed",
        summary="Fans were furious the finale denied the long-teased reunion.",
        key_moments=["showrunner confirms no reunion planned"],
        references=["https://reddit.com/r/x/comments/1", "https://example.com/article"],
        sources=["reddit_search", "tavily_search"],
        apify_cost_estimate=0.86,
    )


def test_decide_next_step_passthrough():
    state = ContextAgentState(
        topic="",
        reddit_text="",
        tavily_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="tavily_search",
        next_query="",
        urls=[],
        summary="",
        key_moments=[],
    )
    result = decide_next_step(state, max_tool_calls=5, max_run_apify_cost=2.00)

    assert result == "tavily_search"


def test_decide_next_step_floor_override_reddit():
    state = ContextAgentState(
        topic="",
        reddit_text="",
        tavily_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="stop",
        next_query="",
        urls=[],
        summary="",
        key_moments=[],
    )
    result = decide_next_step(state, max_tool_calls=5, max_run_apify_cost=2.00)

    assert result == "reddit_search"


def test_decide_next_step_floor_override_tavily():
    state = ContextAgentState(
        topic="",
        reddit_text="",
        tavily_text="",
        reddit_calls=1,
        tavily_calls=0,
        apify_cost_estimate=0.86,
        within_community="",
        next_action="stop",
        next_query="",
        urls=[],
        summary="",
        key_moments=[],
    )
    result = decide_next_step(state, max_tool_calls=5, max_run_apify_cost=2.00)

    assert result == "tavily_search"


def test_decide_next_step_floor_satisfied():
    state = ContextAgentState(
        topic="",
        reddit_text="",
        tavily_text="",
        reddit_calls=1,
        tavily_calls=1,
        apify_cost_estimate=0.86,
        within_community="",
        next_action="stop",
        next_query="",
        urls=[],
        summary="",
        key_moments=[],
    )
    result = decide_next_step(state, max_tool_calls=5, max_run_apify_cost=2.00)

    assert result == "stop"


def test_run_floor_override_uses_topic_not_empty_query(monkeypatch):
    """Regression: when decide_next_step floor-overrides a "stop" into a forced
    tavily call, _act_tavily must search on the topic, not the empty next_query
    the LLM wrote when it intended to stop.

    Pre-fix this recorded [""]; post-fix it records [topic]. The plan-LLM
    sequence forces the override: run reddit, then say "stop" (tavily_calls==0
    triggers the floor override), then say "stop" again (floor now satisfied).
    Three plan calls before finalize.
    """
    recorded_tavily_queries: list[str] = []

    def fake_reddit_search(query, within_community=None):
        return ToolResult(text="top comment: robbed", urls=["https://reddit.com/r/x/comments/1"])

    def fake_tavily_search(query):
        recorded_tavily_queries.append(query)
        return ToolResult(text="background: finale aired June 28", urls=["https://example.com/article"])

    monkeypatch.setattr(context_agent_module, "reddit_search", fake_reddit_search)
    monkeypatch.setattr(context_agent_module, "tavily_search", fake_tavily_search)

    plan_decisions = [
        PlanDecision(next_action="reddit_search", next_query="finale reaction"),
        PlanDecision(next_action="stop", next_query=""),
        PlanDecision(next_action="stop", next_query=""),
    ]
    synthesis = ContextSynthesis(
        summary="Fans were furious the finale denied the long-teased reunion.",
        key_moments=["showrunner confirms no reunion planned"],
    )
    fake = FakeSequenceLLM(plan_decisions=plan_decisions, synthesis=synthesis)
    agent = ContextAgent(llm=fake, max_tool_calls=5)

    agent.run("Wistoria season 2 finale")

    # First entry is _lookup_community's own upfront tavily call (runs once,
    # before the loop, regardless of plan decisions); second is the
    # floor-override call under test.
    assert recorded_tavily_queries == [
        "Wistoria season 2 finale reddit subreddit",
        "Wistoria season 2 finale",
    ], (
        f"floor-override tavily call must use the topic, not empty next_query; "
        f"got {recorded_tavily_queries!r}"
    )