
from src.monitor.schemas import ContextBundle, ContextSynthesis, PlanDecision
from src.monitor.tools import estimate_cost
from src.monitor.tools._types import ToolResult
import src.monitor.context_agent as context_agent_module
from src.monitor.context_agent import (
    ContextAgent,
    build_context_bundle,
    decide_next_step,
    ContextAgentState,
    _truncate_to_whole_blocks,
)
from src.monitor.tools.subreddit_search import COMMUNITY_SEARCH_COST, Subreddit


def _reddit_call_params() -> dict:
    """The reddit-search params _act_reddit is expected to use — read from the
    module's shared constants so these tests and production share one source
    of truth (AUD-M1)."""
    return {
        "max_posts": context_agent_module._REDDIT_MAX_POSTS,
        "max_comments_per_post": context_agent_module._REDDIT_MAX_COMMENTS_PER_POST,
        "max_comments_count": context_agent_module._REDDIT_MAX_COMMENTS_COUNT,
    }


def _expected_reddit_call_cost() -> float:
    """One reddit_search call's estimated cost, priced from the same shared params."""
    return estimate_cost(**_reddit_call_params())


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
        reddit_queries=[],
        tavily_queries=[],
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
        reddit_queries=[],
        tavily_queries=[],
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
        reddit_queries=["Wistoria Elfie Zeo Will episode 11"],
        tavily_queries=[],
        summary="",
        key_moments=[],
    )

    result = agent._plan(state)

    assert result == {"next_action": "reddit_search", "next_query": "Wistoria season 2 finale"}
    assert "Wistoria season 2 finale" in fake.prompt
    # Regression for BUG-023: the planner must see its own past queries so it
    # doesn't repeat one verbatim (observed live on event 8 — see bugs.md).
    assert "Wistoria Elfie Zeo Will episode 11" in fake.prompt


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
        reddit_queries=[],
        tavily_queries=[],
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
    captured_kwargs: list[dict] = []

    def fake_reddit_search(query, within_community=None, **kwargs):
        captured_kwargs.append(kwargs)
        return ToolResult(
            text="fresh reaction text", urls=["https://reddit.com/r/x/comments/1"]
        )

    monkeypatch.setattr(context_agent_module, "reddit_search", fake_reddit_search)
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
        reddit_queries=["earlier query"],
        tavily_queries=[],
        summary="",
        key_moments=[],
    )

    result = agent._act_reddit(state)

    # AUD-M1 regression: the estimate must be priced from the SAME params the
    # call used — the fake captures what reddit_search received, the expected
    # cost is computed from the module's shared constants, and the two must
    # match exactly.
    assert captured_kwargs == [_reddit_call_params()]
    assert result == {
        "reddit_text": "earlier reaction text\n\nfresh reaction text",
        "reddit_calls": 2,
        "apify_cost_estimate": 0.86 + _expected_reddit_call_cost(),
        "urls": ["https://reddit.com/r/x/comments/0", "https://reddit.com/r/x/comments/1"],
        "reddit_queries": ["earlier query", "some query"],
    }


def _fresh_state(topic):
    return ContextAgentState(
        topic=topic, reddit_text="", tavily_text="", reddit_calls=0,
        tavily_calls=0, apify_cost_estimate=0.0, within_community="",
        next_action="", next_query="", urls=[], reddit_queries=[], tavily_queries=[],
        summary="", key_moments=[],
    )


def test_lookup_community_picks_biggest_dedicated(monkeypatch):
    monkeypatch.setattr(
        context_agent_module, "search_subreddits",
        lambda topic: [
            Subreddit("attackontitan", "Attack on Titan", 667068, False),
            Subreddit("ShingekiNoKyojin", "Shingeki No Kyojin (Attack on Titan)", 2463826, False),
        ],
    )
    agent = ContextAgent(llm=object())
    result = agent._lookup_community(_fresh_state("Attack on Titan finale"))
    assert result == {
        "within_community": "r/ShingekiNoKyojin",
        "apify_cost_estimate": COMMUNITY_SEARCH_COST,
    }


def test_lookup_community_matches_on_title_when_name_is_foreign(monkeypatch):
    # name carries no topic token; only the title does — title match is load-bearing
    monkeypatch.setattr(
        context_agent_module, "search_subreddits",
        lambda topic: [
            Subreddit("ShingekiNoKyojin", "Shingeki No Kyojin (Attack on Titan)", 2463826, False)
        ],
    )
    agent = ContextAgent(llm=object())
    result = agent._lookup_community(_fresh_state("Attack on Titan finale"))
    assert result["within_community"] == "r/ShingekiNoKyojin"


def test_lookup_community_drops_nsfw(monkeypatch):
    monkeypatch.setattr(
        context_agent_module, "search_subreddits",
        lambda topic: [
            Subreddit("TitanNSFW", "Attack on Titan NSFW", 9_000_000, True),  # biggest but nsfw
            Subreddit("attackontitan", "Attack on Titan", 667068, False),
        ],
    )
    agent = ContextAgent(llm=object())
    result = agent._lookup_community(_fresh_state("Attack on Titan"))
    assert result["within_community"] == "r/attackontitan"


def test_lookup_community_empty_when_none_pass_token(monkeypatch):
    """BUG-014 invariant preserved: no dedicated sub -> empty -> unscoped
    fallback, never scope to a big unrelated sub."""
    monkeypatch.setattr(
        context_agent_module, "search_subreddits",
        lambda topic: [
            Subreddit("movies", "Movies", 30_000_000, False),
            Subreddit("television", "Television", 18_000_000, False),
        ],
    )
    agent = ContextAgent(llm=object())
    result = agent._lookup_community(_fresh_state("Obsession 2025"))
    assert result == {"within_community": "", "apify_cost_estimate": COMMUNITY_SEARCH_COST}


def test_lookup_community_fail_soft_on_exception(monkeypatch):
    def boom(topic):
        raise RuntimeError("apify down")

    monkeypatch.setattr(context_agent_module, "search_subreddits", boom)
    agent = ContextAgent(llm=object())
    result = agent._lookup_community(_fresh_state("Attack on Titan"))
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
        reddit_queries=[],
        tavily_queries=["earlier web query"],
        summary="",
        key_moments=[],
    )

    result = agent._act_tavily(state)

    assert result == {
        "tavily_text": "background facts",
        "tavily_calls": 1,
        "urls": ["https://example.com/article"],
        "tavily_queries": ["earlier web query", "some query"],
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
        reddit_queries=[],
        tavily_queries=[],
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
        reddit_queries=[],
        tavily_queries=[],
        summary="",
        key_moments=[],
    )

    bundle = build_context_bundle(state)

    assert bundle.sources == []


def test_run_full_loop(monkeypatch):
    monkeypatch.setattr(
        context_agent_module,
        "reddit_search",
        lambda query, within_community=None, **kwargs: ToolResult(
            text="top comment: robbed", urls=["https://reddit.com/r/x/comments/1"]
        ),
    )
    monkeypatch.setattr(
        context_agent_module,
        "tavily_search",
        lambda query: ToolResult(text="background: finale aired June 28", urls=["https://example.com/article"]),
    )
    monkeypatch.setattr(context_agent_module, "search_subreddits", lambda topic: [])

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
        # One reddit call priced at the shared call params, plus the one-time
        # community-lookup Apify cost every Path B run now pays.
        apify_cost_estimate=COMMUNITY_SEARCH_COST + _expected_reddit_call_cost(),
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
        reddit_queries=[],
        tavily_queries=[],
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
        reddit_queries=[],
        tavily_queries=[],
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
        reddit_queries=[],
        tavily_queries=[],
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
        reddit_queries=[],
        tavily_queries=[],
        summary="",
        key_moments=[],
    )
    result = decide_next_step(state, max_tool_calls=5, max_run_apify_cost=2.00)

    assert result == "stop"


def test_truncate_to_whole_blocks_under_budget_unchanged():
    text = "[POST | 10 upvotes] short\n\n[POST | 5 upvotes] also short"
    assert _truncate_to_whole_blocks(text, max_chars=2000) == text


def test_truncate_to_whole_blocks_keeps_whole_blocks_only():
    block_a = "[POST | 100 upvotes] " + "a" * 50
    block_b = "[POST | 90 upvotes] " + "b" * 50
    block_c = "[POST | 80 upvotes] " + "c" * 50
    text = "\n\n".join([block_a, block_b, block_c])

    # budget fits block_a and block_b whole, but not block_c too
    result = _truncate_to_whole_blocks(text, max_chars=len(block_a) + 2 + len(block_b))

    assert result == "\n\n".join([block_a, block_b])
    # BUG-023 follow-up: never cut a block in half.
    assert "c" * 50 not in result
    assert not result.endswith("c")


def test_truncate_to_whole_blocks_first_block_alone_too_big():
    huge_block = "[POST | 1 upvotes] " + "x" * 5000
    result = _truncate_to_whole_blocks(huge_block, max_chars=2000)
    assert result == huge_block[:2000]
    assert len(result) == 2000


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

    def fake_reddit_search(query, within_community=None, **kwargs):
        return ToolResult(text="top comment: robbed", urls=["https://reddit.com/r/x/comments/1"])

    def fake_tavily_search(query):
        recorded_tavily_queries.append(query)
        return ToolResult(text="background: finale aired June 28", urls=["https://example.com/article"])

    monkeypatch.setattr(context_agent_module, "reddit_search", fake_reddit_search)
    monkeypatch.setattr(context_agent_module, "tavily_search", fake_tavily_search)
    monkeypatch.setattr(context_agent_module, "search_subreddits", lambda topic: [])

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

    # _lookup_community no longer makes a tavily call (it uses search_subreddits
    # now), so the only recorded tavily query is the floor-override call under
    # test — which must use the topic, not the empty next_query.
    assert recorded_tavily_queries == ["Wistoria season 2 finale"], (
        f"floor-override tavily call must use the topic, not empty next_query; "
        f"got {recorded_tavily_queries!r}"
    )