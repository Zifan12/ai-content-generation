"""
Debug script: probe whether searchSort="top" + withinCommunity together
return relevant, upvote-ordered posts.

WHY THIS EXISTS:
  BUG-004 (bugs.md) found that searchSort="top" alone ignores searchTerms
  and returns generic Reddit-wide top posts. The actor's docs give zero
  info on whether combining "top" with withinCommunity (scoping to one
  subreddit) changes that — no cross-reference between the two fields
  anywhere in the schema. Rather than guess and burn a real reddit_search
  call in the actual pipeline, this is a minimal, cheap, standalone probe:
  posts only, no comments, small max_posts, so a run costs cents not
  dollars.

  Deliberately NOT built on top of reddit_search.py — that function
  hardcodes searchSort="relevance" (the confirmed-working value after
  BUG-004) and has no reason to expose a "top" escape hatch for
  production callers. This script builds its own run_input directly so
  the experiment stays isolated from the real tool.

USAGE:
  uv run python scripts/probe_reddit_sort_community.py "Wistoria Elfie Zeovs" --community r/Wistoria
  uv run python scripts/probe_reddit_sort_community.py "<query>" --community r/<name> --max-posts 3

  Prints estimated cost before calling, then each returned post's title,
  score, and subreddit, in the order the actor returned them. Eyeball:
  (a) are they all actually about the query, (b) does the order look
  upvote-sorted (high score first)?

DISCARD AFTER:
  Throwaway probe for one specific open question. Delete once answered.
"""

import argparse
import os

from dotenv import load_dotenv
import httpx

from src.monitor.tools.reddit_search import estimate_cost

load_dotenv("config/.env")

_APIFY_BASE_URL = "https://api.apify.com/v2"
_ACTOR_ID = "harshmaur/reddit-scraper"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Search phrase (e.g. 'Wistoria Elfie Zeovs')")
    parser.add_argument("--community", required=True, help="e.g. r/Wistoria")
    parser.add_argument("--max-posts", type=int, default=3)
    args = parser.parse_args()

    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise SystemExit("APIFY_API_TOKEN not set in config/.env")

    estimated = estimate_cost(max_posts=args.max_posts, max_comments_per_post=0, max_comments_count=0)
    print(f"Estimated cost: ${estimated:.4f} ({args.max_posts} posts, no comments)")

    run_input = {
        "searchTerms": [args.query],
        "searchPosts": True,
        "searchComments": False,
        "maxPostsCount": args.max_posts,
        "crawlCommentsPerPost": False,
        "searchSort": "top",
        "withinCommunity": args.community,
        "includeNSFW": False,
        "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
    }

    actor_path = _ACTOR_ID.replace("/", "~")
    url = f"{_APIFY_BASE_URL}/acts/{actor_path}/run-sync-get-dataset-items"
    response = httpx.post(url, params={"token": token}, json=run_input, timeout=120.0)
    response.raise_for_status()
    items = response.json()

    posts = [item for item in items if item.get("dataType") == "post"]
    if not posts:
        print("No posts returned.")
        return

    print(f"\n{len(posts)} post(s) returned, in actor order:\n")
    for i, post in enumerate(posts, start=1):
        score = post.get("score")
        if score is None:
            score = post.get("upVotes")
        community = post.get("parsedCommunityName") or post.get("communityName")
        title = (post.get("title") or "").encode("ascii", "replace").decode("ascii")
        print(f"{i}. [score={score}] r/{community} — {title}")


if __name__ == "__main__":
    main()
