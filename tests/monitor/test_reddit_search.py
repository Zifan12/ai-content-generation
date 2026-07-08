"""Unit tests for reddit_search's comment noise floor (spec D7).

All tests inject ``item_fetcher`` so parsing/shaping is exercised with no
network and no Apify token.
"""

from src.monitor.tools.reddit_search import reddit_search


def _post_and_comments(comment_scores):
    items = [
        {"dataType": "post", "id": "t3_abc", "postId": "t3_abc",
         "title": "Some post", "score": 500, "postUrl": "https://reddit.com/p/abc"},
    ]
    for i, score in enumerate(comment_scores):
        items.append({
            "dataType": "comment", "postId": "t3_abc",
            "score": score, "body": f"comment {i} (score {score})",
        })
    return items


def test_drops_comments_under_five_upvotes():
    items = _post_and_comments([4, 5, -3, 0, 1000])
    result = reddit_search("x", item_fetcher=lambda run_input: items)
    assert "comment 0 (score 4)" not in result.text
    assert "comment 2 (score -3)" not in result.text
    assert "comment 3 (score 0)" not in result.text
    assert "comment 1 (score 5)" in result.text
    assert "comment 4 (score 1000)" in result.text


def test_post_with_no_surviving_comments_still_gets_its_own_block():
    items = _post_and_comments([1, 2, -1])
    result = reddit_search("x", item_fetcher=lambda run_input: items)
    assert "Some post" in result.text
    assert "comment" not in result.text.lower().split("some post")[1]
