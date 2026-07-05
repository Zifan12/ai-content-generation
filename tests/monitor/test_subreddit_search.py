"""Unit tests for the search_subreddits community-search tool.

All tests inject ``item_fetcher`` so parsing/shaping is exercised with no
network and no Apify token.
"""

from src.monitor.tools.subreddit_search import Subreddit, search_subreddits


def test_parses_communities_and_coerces_members():
    items = [
        {"name": "ShingekiNoKyojin", "title": "Shingeki No Kyojin (Attack on Titan)",
         "membersCount": 2463826, "nsfw": False},
        {"name": "attackontitan", "title": "Attack on Titan", "membersCount": 667068, "nsfw": False},
    ]
    result = search_subreddits("attack on titan", item_fetcher=lambda run_input: items)
    assert result == [
        Subreddit("ShingekiNoKyojin", "Shingeki No Kyojin (Attack on Titan)", 2463826, False),
        Subreddit("attackontitan", "Attack on Titan", 667068, False),
    ]


def test_missing_members_count_becomes_zero():
    items = [{"name": "SomeSub", "title": "Some Sub", "nsfw": False}]
    result = search_subreddits("x", item_fetcher=lambda run_input: items)
    assert result[0].members == 0


def test_skips_items_without_name():
    items = [{"title": "no name", "membersCount": 5},
             {"name": "Good", "title": "t", "membersCount": 3, "nsfw": False}]
    result = search_subreddits("x", item_fetcher=lambda run_input: items)
    assert [s.name for s in result] == ["Good"]


def test_run_input_requests_community_search():
    captured = {}

    def fake(run_input):
        captured.update(run_input)
        return []

    search_subreddits("attack on titan", item_fetcher=fake, max_communities=8)
    assert captured["searchCommunities"] is True
    assert captured["searchPosts"] is False
    assert captured["maxCommunitiesCount"] == 8
    assert captured["searchTerms"] == ["attack on titan"]
