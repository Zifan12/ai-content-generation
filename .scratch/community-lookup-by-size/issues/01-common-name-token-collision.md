# `_lookup_community`'s token match is substring, not word-boundary — a common first name collides with an unrelated, bigger subreddit

Status: ready-for-human

`_lookup_community`'s dedicated-sub filter (`src/monitor/context_agent.py:236-238`) checks membership with `token in haystack` — Python substring containment, not a word-boundary match:

```
def _dedicated(sub: Subreddit) -> bool:
    haystack = f"{sub.name} {sub.title}".lower()
    return any(token in haystack for token in topic_tokens)
```

`topic_tokens` only filters by length (`>= 4`, line 233), not by how generic the word is. A topic containing a common first name will match ANY subreddit whose name or title happens to contain that name as a substring, dedicated or not.

## Evidence

Live Path B dry-run, 2026-07-04, topic: *"Obsession (2025) fans wishing the movie had kept its deleted alternate ending, where Nikki Freeman gets free instead of the dark fate Bear's wish trapped her in"*.

`context_agent.lookup_community` resolved `within_community` to **r/InfinityNikki** — a real, unrelated video-game subreddit — instead of failing soft to unscoped (there is apparently no large dedicated sub for this movie). Langfuse observation `bda3a3b35d33c10c`, trace `331902adbd6d829fe881136325f2e44b`, output: `{"within_community": "r/InfinityNikki", "apify_cost_estimate": 0.035}`.

Root cause: `"nikki"` (5 chars, passes the length filter) is a substring of `"InfinityNikki"`. r/InfinityNikki has enough members to win the biggest-survivor tiebreak (`context_agent.py:247`) against whatever small/nonexistent dedicated community exists for the actual movie.

This is the same *class* of bug the `search_subreddits` rewrite (commit `befabbb`) was built to fix (r/titanfolk beating r/ShingekiNoKyojin on a `"titan"` substring match) — but that fix changed the candidate *pool* (community-search API results instead of scraped Tavily URLs), not the match *primitive*. The primitive is still naive substring containment, so it reproduces the same failure whenever a topic's key noun is also a generic word or common first name that happens to substring-match an unrelated, larger community.

## Why the original fix didn't catch this

The AoT (`titan` → titanfolk) and Wistoria (`wistoria` → r/Wistoria) cases both happened to have a genuinely dedicated, correctly-named subreddit in the candidate pool, so the substring match landed on the right answer by luck of vocabulary, not by design. A topic anchored on a common first name with no dedicated home subreddit exposes the gap.

## Fix direction (not decided — needs a design call)

Options to weigh, not a prescribed fix:
- Require a minimum topic-token length beyond 4, or exclude common-name tokens specifically (fragile — needs a name list).
- Word-boundary match instead of substring (`re.search(rf"\b{token}\b", haystack)`) — would still not distinguish "Nikki" the person from "Nikki" the game, since both are literal word matches.
- Require the match on a token from the IP/title (e.g. "Obsession") rather than a character name, since character first names are far more likely to collide with unrelated fandoms/games/people.
- Add a members-floor-relative-to-pool check (e.g. reject if the winning candidate's token match is weak character-only when a title-level candidate — even a small one — exists) — trades against D5's explicit "no members-floor" decision, so revisit that decision's rationale before doing this.

Touches `_lookup_community`'s matching heuristic — a design decision (which token, which surface, how strict), not a mechanical fix. Ready-for-human per this project's convention for decision-bearing monitor logic.

## Comments
