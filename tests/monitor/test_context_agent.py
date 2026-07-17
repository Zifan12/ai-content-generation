
from src.monitor.schemas import (
    BriefFieldDraft,
    ContextBundle,
    ContextSynthesis,
    PlanDecision,
    TopicBrief,
    TopicBriefDraft,
)
from src.monitor.tools import estimate_cost
from src.monitor.tools._types import ToolResult
import src.monitor.context_agent as context_agent_module
from src.monitor.context_agent import (
    ContextAgent,
    build_context_bundle,
    compose_topic_brief,
    decide_next_step,
    ContextAgentState,
    PLAN_SYSTEM_PROMPT,
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
        web_text="",
        reddit_calls=3,
        tavily_calls=2,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="reddit_search",
        next_query="",
        urls=[],
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )
    result = decide_next_step(
        state, max_tool_calls=5, max_run_apify_cost=2.00, max_consecutive_stale_reddit_calls=3
    )

    assert result == "stop"


def test_decide_next_step_apify_cost_ceiling():
    """The cumulative Apify cost ceiling overrides everything, same as
    max_tool_calls — even when total_calls is well under the cap and the
    LLM wants to keep searching Reddit.
    """
    state = ContextAgentState(
        topic="",
        reddit_text="",
        web_text="",
        reddit_calls=1,
        tavily_calls=0,
        apify_cost_estimate=2.00,
        within_community="",
        next_action="reddit_search",
        next_query="",
        urls=[],
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )
    result = decide_next_step(
        state, max_tool_calls=5, max_run_apify_cost=2.00, max_consecutive_stale_reddit_calls=3
    )

    assert result == "stop"


def test_decide_next_step_stale_streak_ceiling():
    """BUG-026 regression: the saturation guard overrides the LLM's own
    next_action, same as the cost ceiling — even when calls/cost are both
    well under their caps."""
    state = ContextAgentState(
        topic="",
        reddit_text="",
        web_text="",
        reddit_calls=3,
        tavily_calls=0,
        apify_cost_estimate=0.39,
        within_community="",
        next_action="reddit_search",
        next_query="one more phrase",
        urls=[],
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=3,
    )
    result = decide_next_step(
        state, max_tool_calls=20, max_run_apify_cost=1.50, max_consecutive_stale_reddit_calls=3
    )

    assert result == "stop"


def test_plan_returns_llm_decision():
    decision = PlanDecision(next_action="reddit_search", next_query="Wistoria season 2 finale")
    fake = FakePlanLLM(decision=decision)
    agent = ContextAgent(llm=fake)
    state = ContextAgentState(
        topic="Wistoria season 2 finale",
        reddit_text="",
        web_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="",
        next_query="",
        urls=[],
        reddit_queries=["Wistoria Elfie Zeo Will episode 11"],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )

    result = agent._plan(state)

    assert result == {
        "next_action": "reddit_search",
        "next_query": "Wistoria season 2 finale",
        "next_url": "",
    }
    assert "Wistoria season 2 finale" in fake.prompt
    # Regression for BUG-023: the planner must see its own past queries so it
    # doesn't repeat one verbatim (observed live on event 8 — see bugs.md).
    assert "Wistoria Elfie Zeo Will episode 11" in fake.prompt


def test_plan_threads_next_url_for_firecrawl_extract():
    """Regression: _plan's return dict must include next_url, not just
    next_action/next_query. LangGraph only applies state keys a node's
    return dict includes, so a firecrawl_extract decision with a real
    next_url that _plan dropped would leave state.next_url stuck at "" —
    and _act_firecrawl_extract's exact-match guard (state.next_url not in
    state.urls) would then silently no-op on every real run."""
    decision = PlanDecision(
        next_action="firecrawl_extract",
        next_query="",
        next_url="https://example.com/wiki/X",
    )
    fake = FakePlanLLM(decision=decision)
    agent = ContextAgent(llm=fake)
    state = _fresh_state("Wistoria season 2 finale")

    result = agent._plan(state)

    assert result["next_url"] == "https://example.com/wiki/X"


def test_plan_system_prompt_targets_specific_ambiguity():
    """The planner must be told to search for a SPECIFIC unclear fact, not a
    generic background search — otherwise tavily_search fires every run
    (guaranteed by decide_next_step's floor) without reliably resolving the
    thing that actually needs verifying (see spec 2026-07-07-path-b-targeted-
    grounding-design.md)."""
    assert "specific unclear thing" in PLAN_SYSTEM_PROMPT
    assert "not a generic topic search" in PLAN_SYSTEM_PROMPT


def test_finalize_returns_llm_synthesis():
    synthesis = ContextSynthesis(
        summary="Fans were furious the finale denied the long-teased reunion.",
        key_moments=["showrunner confirms no reunion planned"],
        unresolved_facts=["whether the showrunner's quote was sarcastic"],
    )
    fake = FakeFinalizeLLM(synthesis=synthesis)
    agent = ContextAgent(llm=fake)
    state = ContextAgentState(
        topic="Wistoria season 2 finale",
        reddit_text="top comment: robbed",
        web_text="background: finale aired June 28",
        reddit_calls=1,
        tavily_calls=1,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="stop",
        next_query="",
        urls=[],
        reddit_queries=[],
        tavily_queries=["is the reunion confirmed cut"],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )

    result = agent._finalize(state)

    assert result == {
        "summary": "Fans were furious the finale denied the long-teased reunion.",
        "key_moments": ["showrunner confirms no reunion planned"],
        "unresolved_facts": ["whether the showrunner's quote was sarcastic"],
    }
    assert "top comment: robbed" in fake.prompt
    assert "background: finale aired June 28" in fake.prompt
    # BUG-023-follow-up regression: finalize must see what was SEARCHED FOR
    # (not just what was found) to judge what's actually unresolved.
    assert "is the reunion confirmed cut" in fake.prompt


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
        web_text="",
        reddit_calls=1,
        tavily_calls=0,
        apify_cost_estimate=0.86,
        within_community="",
        next_action="reddit_search",
        next_query="some query",
        urls=["https://reddit.com/r/x/comments/0"],
        reddit_queries=["earlier query"],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
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
        "consecutive_stale_reddit_calls": 0,
    }


def test_act_reddit_resets_stale_streak_when_new_url_found(monkeypatch):
    """BUG-026 regression: a call that finds even one genuinely new URL must
    reset the streak, not just start it at 0 — proves reset, not default."""
    monkeypatch.setattr(
        context_agent_module,
        "reddit_search",
        lambda query, within_community=None, **kwargs: ToolResult(
            text="fresh", urls=["https://reddit.com/r/x/comments/new"]
        ),
    )
    agent = ContextAgent(llm=object())
    state = _fresh_state("Wistoria").model_copy(
        update={
            "urls": ["https://reddit.com/r/x/comments/old"],
            "consecutive_stale_reddit_calls": 2,
        }
    )

    result = agent._act_reddit(state)

    assert result["consecutive_stale_reddit_calls"] == 0


def test_act_reddit_increments_stale_streak_when_no_new_urls(monkeypatch):
    """BUG-026 regression: a call that returns only already-seen URLs must
    increment the streak instead of resetting it."""
    monkeypatch.setattr(
        context_agent_module,
        "reddit_search",
        lambda query, within_community=None, **kwargs: ToolResult(
            text="same old", urls=["https://reddit.com/r/x/comments/old"]
        ),
    )
    agent = ContextAgent(llm=object())
    state = _fresh_state("Wistoria").model_copy(
        update={
            "urls": ["https://reddit.com/r/x/comments/old"],
            "consecutive_stale_reddit_calls": 1,
        }
    )

    result = agent._act_reddit(state)

    assert result["consecutive_stale_reddit_calls"] == 2


def test_act_firecrawl_extract_skips_unknown_url(monkeypatch, caplog):
    """D4: next_url must exact-match something already in state.urls, else
    the call is skipped (fail-soft), not made — prevents the LLM targeting a
    hallucinated/recalled URL never actually found by a real search."""
    called = []
    monkeypatch.setattr(
        context_agent_module, "firecrawl_extract",
        lambda url, **kwargs: called.append(url) or ToolResult(text="x", urls=[]),
    )
    agent = ContextAgent(llm=object())
    state = _fresh_state("Wistoria")
    state = state.model_copy(update={
        "next_url": "https://example.com/never-found",
        "urls": ["https://example.com/actually-found"],
        "web_text": "existing",
    })

    result = agent._act_firecrawl_extract(state)

    assert called == []
    assert result == {"tavily_calls": 1}


def test_act_firecrawl_extract_appends_on_success(monkeypatch):
    monkeypatch.setattr(
        context_agent_module, "firecrawl_extract",
        lambda url, **kwargs: ToolResult(text="Age: 16", urls=[]),
    )
    agent = ContextAgent(llm=object())
    state = _fresh_state("Wistoria")
    state = state.model_copy(update={
        "next_url": "https://wistoria.fandom.com/wiki/Elfaria",
        "urls": ["https://wistoria.fandom.com/wiki/Elfaria"],
        "web_text": "earlier web text",
        "tavily_calls": 1,
        "tavily_queries": ["Wistoria characters"],
    })

    result = agent._act_firecrawl_extract(state)

    assert result == {
        "web_text": "earlier web text\n\nAge: 16",
        "tavily_calls": 2,
        "tavily_queries": [
            "Wistoria characters",
            "https://wistoria.fandom.com/wiki/Elfaria",
        ],
    }


def test_act_firecrawl_extract_fails_soft_on_fetch_error(monkeypatch):
    def raising(url, **kwargs):
        raise RuntimeError("Failed to fetch url")

    monkeypatch.setattr(context_agent_module, "firecrawl_extract", raising)
    agent = ContextAgent(llm=object())
    state = _fresh_state("Wistoria")
    state = state.model_copy(update={
        "next_url": "https://wistoria.fandom.com/wiki/Elfaria",
        "urls": ["https://wistoria.fandom.com/wiki/Elfaria"],
    })

    result = agent._act_firecrawl_extract(state)

    assert result == {"tavily_calls": 1}


def test_act_firecrawl_extract_failure_counts_toward_loop_termination_cap(monkeypatch):
    """The empirically-demonstrated infinite-loop gap: if the LLM planner keeps
    picking firecrawl_extract and it keeps failing, decide_next_step's
    total_calls ceiling is the only thing that stops the loop (see
    _DEFAULT_MAX_TOOL_CALLS). That only works if a failed attempt still
    increments tavily_calls. Drive one failing call from one call short of
    the cap and confirm decide_next_step now says "stop"."""

    def raising(url, **kwargs):
        raise RuntimeError("Failed to fetch url")

    monkeypatch.setattr(context_agent_module, "firecrawl_extract", raising)
    agent = ContextAgent(llm=object())
    state = _fresh_state("Wistoria")
    state = state.model_copy(update={
        "next_url": "https://wistoria.fandom.com/wiki/Elfaria",
        "urls": ["https://wistoria.fandom.com/wiki/Elfaria"],
        "reddit_calls": 0,
        "tavily_calls": agent.max_tool_calls - 1,
    })

    result = agent._act_firecrawl_extract(state)
    state_after = state.model_copy(update=result)

    assert decide_next_step(
        state_after,
        max_tool_calls=agent.max_tool_calls,
        max_run_apify_cost=agent.max_run_apify_cost,
        max_consecutive_stale_reddit_calls=agent.max_consecutive_stale_reddit_calls,
    ) == "stop"


def test_plan_system_prompt_mentions_firecrawl_extract():
    assert "firecrawl_extract" in PLAN_SYSTEM_PROMPT


def test_max_tool_calls_default_is_20():
    agent = ContextAgent(llm=object())
    assert agent.max_tool_calls == 20


def _fresh_state(topic):
    return ContextAgentState(
        topic=topic, reddit_text="", web_text="", reddit_calls=0,
        tavily_calls=0, apify_cost_estimate=0.0, within_community="",
        next_action="", next_query="", urls=[], reddit_queries=[], tavily_queries=[],
        unresolved_facts=[], summary="", key_moments=[],
        consecutive_stale_reddit_calls=0,
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
        web_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="tavily_search",
        next_query="some query",
        urls=[],
        reddit_queries=[],
        tavily_queries=["earlier web query"],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )

    result = agent._act_tavily(state)

    assert result == {
        "web_text": "background facts",
        "tavily_calls": 1,
        "urls": ["https://example.com/article"],
        "tavily_queries": ["earlier web query", "some query"],
    }


def test_build_context_bundle_both_sources():
    state = ContextAgentState(
        topic="",
        reddit_text="top comment: robbed",
        web_text="background: finale aired June 28",
        reddit_calls=1,
        tavily_calls=1,
        apify_cost_estimate=0.86,
        within_community="",
        next_action="stop",
        next_query="",
        urls=["https://reddit.com/r/x/comments/1", "https://example.com/article"],
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=[],
        summary="Fans were furious the finale denied the long-teased reunion.",
        key_moments=["showrunner confirms no reunion planned"],
        consecutive_stale_reddit_calls=0,
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
        web_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="stop",
        next_query="",
        urls=[],
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )

    bundle = build_context_bundle(state)

    assert bundle.sources == []


def test_build_context_bundle_threads_unresolved_facts():
    state = ContextAgentState(
        topic="",
        reddit_text="top comment: robbed",
        web_text="",
        reddit_calls=1,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="stop",
        next_query="",
        urls=[],
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=["whether the lead character is confirmed dead"],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )

    bundle = build_context_bundle(state)

    assert bundle.unresolved_facts == ["whether the lead character is confirmed dead"]


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

    bundle, _ = agent.run("Wistoria season 2 finale")

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
        web_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="tavily_search",
        next_query="",
        urls=[],
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )
    result = decide_next_step(
        state, max_tool_calls=5, max_run_apify_cost=2.00, max_consecutive_stale_reddit_calls=3
    )

    assert result == "tavily_search"


def test_decide_next_step_floor_override_reddit():
    state = ContextAgentState(
        topic="",
        reddit_text="",
        web_text="",
        reddit_calls=0,
        tavily_calls=0,
        apify_cost_estimate=0.0,
        within_community="",
        next_action="stop",
        next_query="",
        urls=[],
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )
    result = decide_next_step(
        state, max_tool_calls=5, max_run_apify_cost=2.00, max_consecutive_stale_reddit_calls=3
    )

    assert result == "reddit_search"


def test_decide_next_step_floor_override_tavily():
    state = ContextAgentState(
        topic="",
        reddit_text="",
        web_text="",
        reddit_calls=1,
        tavily_calls=0,
        apify_cost_estimate=0.86,
        within_community="",
        next_action="stop",
        next_query="",
        urls=[],
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )
    result = decide_next_step(
        state, max_tool_calls=5, max_run_apify_cost=2.00, max_consecutive_stale_reddit_calls=3
    )

    assert result == "tavily_search"


def test_decide_next_step_floor_satisfied():
    state = ContextAgentState(
        topic="",
        reddit_text="",
        web_text="",
        reddit_calls=1,
        tavily_calls=1,
        apify_cost_estimate=0.86,
        within_community="",
        next_action="stop",
        next_query="",
        urls=[],
        reddit_queries=[],
        tavily_queries=[],
        unresolved_facts=[],
        summary="",
        key_moments=[],
        consecutive_stale_reddit_calls=0,
    )
    result = decide_next_step(
        state, max_tool_calls=5, max_run_apify_cost=2.00, max_consecutive_stale_reddit_calls=3
    )

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


# ---------------------------------------------------------------------------
# Exilus lane (PRD ticket 02): _finalize_brief / gather_brief / reenter_with_query
# ---------------------------------------------------------------------------


def _sample_brief_draft() -> TopicBriefDraft:
    return TopicBriefDraft(
        identity=BriefFieldDraft(
            content="Wistoria: Wand and Sword is a fantasy anime.",
            citations=["https://reddit.com/r/x/comments/1"],
        ),
        recent_events=BriefFieldDraft(
            content="Season 2 finale aired June 28.",
            citations=["https://example.com/article"],
        ),
        key_characters=BriefFieldDraft(
            content="Elfaria and Will are the central pair.",
            citations=["https://reddit.com/r/x/comments/1"],
        ),
        why_people_care=BriefFieldDraft(
            content="Fans wanted the long-teased reunion and didn't get it.",
            citations=["https://example.com/article"],
        ),
        open_unknowns=["whether the showrunner's quote was sarcastic"],
    )


class FakeBriefLLM:
    """Same single-call fake pattern as FakeFinalizeLLM, for _finalize_brief."""

    def __init__(self, draft: TopicBriefDraft) -> None:
        self._draft = draft

    def parse(self, prompt: str, response_model: type, **kwargs) -> TopicBriefDraft:
        self.prompt = prompt
        return self._draft


class FakeBriefSequenceLLM:
    """Drives gather_brief()/reenter_with_query() end-to-end: queued
    PlanDecisions for _plan's calls (dispatched by response_model), then a
    fixed TopicBriefDraft for _finalize_brief's call(s).
    """

    def __init__(self, plan_decisions: list[PlanDecision], draft: TopicBriefDraft) -> None:
        self._plan_decisions = list(plan_decisions)
        self._draft = draft

    def parse(self, prompt: str, response_model: type, **kwargs):
        if response_model is PlanDecision:
            return self._plan_decisions.pop(0)
        return self._draft


def test_finalize_brief_returns_composed_draft():
    """AC1: _finalize_brief produces a brief_draft carrying exactly the five
    TopicBrief fields (identity/recent_events/key_characters/why_people_care/
    open_unknowns)."""
    draft = _sample_brief_draft()
    fake = FakeBriefLLM(draft=draft)
    agent = ContextAgent(llm=fake)
    state = _fresh_state("Wistoria season 2 finale")

    result = agent._finalize_brief(state)

    assert result == {"brief_draft": draft}


def test_finalize_brief_prompt_includes_citable_urls():
    """AC5: the finalize-brief node's prompt must include the full set of
    URLs gathered during the run (state.urls) as the citable source list —
    same grounding discipline _plan's prompt already applies elsewhere."""
    fake = FakeBriefLLM(draft=_sample_brief_draft())
    agent = ContextAgent(llm=fake)
    state = _fresh_state("Wistoria season 2 finale").model_copy(
        update={"urls": ["https://reddit.com/r/x/comments/1", "https://example.com/article"]}
    )

    agent._finalize_brief(state)

    assert "https://reddit.com/r/x/comments/1" in fake.prompt
    assert "https://example.com/article" in fake.prompt


def test_compose_topic_brief_maps_all_fields_and_citations():
    """AC1/AC2: composition carries every field's content AND citations
    through untouched, with verified defaulting True (no checker yet)."""
    draft = _sample_brief_draft()

    brief = compose_topic_brief(draft)

    assert isinstance(brief, TopicBrief)
    assert brief.identity.content == draft.identity.content
    assert brief.identity.citations == draft.identity.citations
    assert brief.identity.verified is True
    assert brief.recent_events.citations == draft.recent_events.citations
    assert brief.key_characters.citations == draft.key_characters.citations
    assert brief.why_people_care.citations == draft.why_people_care.citations
    assert brief.open_unknowns == draft.open_unknowns
    # AC2: each of these four fields carries at least one citation in this
    # canned draft, and composition must not drop them.
    for field in (brief.identity, brief.recent_events, brief.key_characters, brief.why_people_care):
        assert len(field.citations) >= 1


def test_topic_brief_has_no_wave_status_or_visual_fields():
    """AC3/AC4 regression guard: the PRD explicitly rejected a wave_status
    field and any visual/lore-dump field on this artifact."""
    field_names = set(TopicBrief.model_fields.keys())
    assert "wave_status" not in field_names
    assert not any("visual" in name or "lore" in name for name in field_names)


def test_gather_brief_wire(monkeypatch):
    """Driver-level wire test (topic in -> TopicBrief out), all fakes injected
    — mirrors the existing test_run_full_loop convention for the brief lane."""
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
        lambda query: ToolResult(
            text="background: finale aired June 28", urls=["https://example.com/article"]
        ),
    )
    monkeypatch.setattr(context_agent_module, "search_subreddits", lambda topic: [])

    plan_decisions = [
        PlanDecision(next_action="reddit_search", next_query="finale reaction"),
        PlanDecision(next_action="tavily_search", next_query="finale background"),
        PlanDecision(next_action="stop", next_query=""),
    ]
    draft = _sample_brief_draft()
    fake = FakeBriefSequenceLLM(plan_decisions=plan_decisions, draft=draft)
    agent = ContextAgent(llm=fake, max_tool_calls=5)

    brief, bundle, web_text, final_state = agent.gather_brief("Wistoria season 2 finale")

    assert brief == compose_topic_brief(draft)
    assert web_text == "background: finale aired June 28"
    assert bundle.references == [
        "https://reddit.com/r/x/comments/1",
        "https://example.com/article",
    ]
    assert final_state.reddit_calls == 1
    assert final_state.tavily_calls == 1


def test_reenter_with_query_carries_budget_cumulatively(monkeypatch):
    """AC8: re-entering with a forced follow-up query must respect the
    REMAINING budget, not a fresh ceiling — total calls across the initial
    run and the re-entry pass together never exceed max_tool_calls."""
    call_log: list[str] = []

    def fake_reddit_search(query, within_community=None, **kwargs):
        call_log.append(query)
        return ToolResult(text="more reaction", urls=[f"https://reddit.com/r/x/comments/{len(call_log)}"])

    monkeypatch.setattr(context_agent_module, "reddit_search", fake_reddit_search)

    # After the forced reddit_search call, _drive_loop calls _plan again
    # (mirrors build_graph's act -> plan edge) — queue a "stop" for it. The
    # ceiling (reddit_calls now 3 == max_tool_calls) would force a stop
    # regardless, but _plan must still return something typed as a
    # PlanDecision, not the brief draft.
    fake = FakeBriefSequenceLLM(
        plan_decisions=[PlanDecision(next_action="stop", next_query="")],
        draft=_sample_brief_draft(),
    )
    agent = ContextAgent(llm=fake, max_tool_calls=3)

    # Simulate a finished initial run that already consumed 2 of the 3
    # allowed tool calls (reddit_calls=2), with next_action="stop" (as a
    # real finished run's last _plan call would leave it).
    state = _fresh_state("Wistoria season 2 finale").model_copy(
        update={"reddit_calls": 2, "tavily_calls": 0, "next_action": "stop"}
    )

    final_state = agent.reenter_with_query(state, action="reddit_search", query="follow-up query")

    # Only ONE more reddit_search call was allowed (2 already spent, cap=3) —
    # the forced call runs once, then decide_next_step's ceiling stops the
    # loop before a second one fires.
    assert call_log == ["follow-up query"]
    assert final_state.reddit_calls == 3
    assert final_state.brief_draft is not None


def test_reenter_with_query_refuses_when_budget_already_exhausted(monkeypatch):
    """AC8 edge: if the passed-in state already sits at the ceiling, the
    forced call must not run at all — decide_next_step's hard ceiling is
    checked before the forced action, same as any other loop iteration."""
    call_log: list[str] = []
    monkeypatch.setattr(
        context_agent_module,
        "reddit_search",
        lambda query, within_community=None, **kwargs: call_log.append(query)
        or ToolResult(text="x", urls=["https://reddit.com/r/x/comments/new"]),
    )

    agent = ContextAgent(llm=FakeBriefLLM(draft=_sample_brief_draft()), max_tool_calls=2)
    state = _fresh_state("Wistoria season 2 finale").model_copy(
        update={"reddit_calls": 2, "tavily_calls": 0, "next_action": "stop"}
    )

    final_state = agent.reenter_with_query(state, action="reddit_search", query="follow-up")

    assert call_log == []
    assert final_state.reddit_calls == 2
    assert final_state.brief_draft is not None


def test_reenter_with_query_refuses_when_apify_cost_already_at_ceiling(monkeypatch):
    """AC8, other half: the cumulative Apify-cost ceiling must also be carried
    forward and checked BEFORE the forced action fires — not just the
    tool-call ceiling. decide_next_step checks apify_cost_estimate before
    next_action, so this isolates that clause specifically."""
    call_log: list[str] = []
    monkeypatch.setattr(
        context_agent_module,
        "reddit_search",
        lambda query, within_community=None, **kwargs: call_log.append(query)
        or ToolResult(text="x", urls=["https://reddit.com/r/x/comments/new"]),
    )

    agent = ContextAgent(
        llm=FakeBriefLLM(draft=_sample_brief_draft()),
        max_tool_calls=20,
        max_run_apify_cost=1.00,
    )
    state = _fresh_state("Wistoria season 2 finale").model_copy(
        update={"reddit_calls": 1, "apify_cost_estimate": 1.00, "next_action": "stop"}
    )

    final_state = agent.reenter_with_query(state, action="reddit_search", query="follow-up")

    assert call_log == []
    assert final_state.apify_cost_estimate == 1.00
    assert final_state.brief_draft is not None