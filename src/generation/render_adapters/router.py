from src.generation.render_adapters.rules import RenderRules
from src.schemas.generation import Shot, Device


def pick_model(tag: str, rules: RenderRules, available: set[str] | None = None) -> str:
    """Pick the highest-preference renderable model for a routing tag.

    ``rules.route(tag)`` yields the ranked (best-first) cli_id list — the
    preference order baked into the YAML. ``available`` is the runtime reality
    filter: the set of model cli_ids actually usable right now (e.g. exposed by
    the current Higgsfield CLI, or deliberately restricted for a cheap test).
    This returns the first model in preference order that is also in
    ``available`` — i.e. the best available choice, degrading gracefully down
    the ranked list when top picks are not usable.

    ``available=None`` means "assume everything is available" and returns the
    top-ranked model unconditionally — the common, unconstrained call.

    Raises:
        ValueError: if ``available`` is a set that excludes every model routed
            for ``tag`` — there is no renderable choice to return. This is a
            caller-side error (the caller chose the restriction), so it fails
            loudly here, naming the tag, the routed list and the available set,
            rather than returning ``None`` and surfacing a cryptic error
            downstream when the missing model id is used.
    """
    list_of_models = rules.route(tag)

    if available is None:
        return list_of_models[0]

    for model in list_of_models:
        if model in available:
            return model

    raise ValueError(
        f"No model routed for tag {tag!r} is available: "
        f"routed {list_of_models!r}, available {available!r}."
    )

def classify_motion(shot: Shot, device: Device) -> str:
    """Classify a shot's motion text into a routing tag.

    Scans the shot's free-text ``motion`` (lowercased) for trigger keywords and
    returns the matching routing tag — the bridge from the writer's English
    prose to a tag ``pick_model`` can route. Falls back to "default" when no
    keyword group matches.

    Precedence matters: groups are checked most-specific first, and the first
    match wins (early return). impossible_physics is checked BEFORE fluid_motion
    so a shot like "water drains inward, edges stay full" — which contains both
    a fluid word ("water"/"drains") and an impossible-physics signal ("edges
    stay") — classifies as impossible_physics, not fluid_motion. Reordering
    these branches changes the routing, so order is load-bearing.

    ``device`` is accepted as a tiebreaker signal but unused in v1 — the keyword
    scan alone settles the current cases.

    This is a deliberate v1 keyword heuristic (cheap, deterministic, testable).
    It matches surface words, not meaning, so paraphrases slip through to
    "default"; the cost of a miss is a non-optimal model, not a failure. The
    designed upgrade path is to swap this one function for an LLM classifier
    (semantic understanding) without touching the rest of the pipeline.
    """
    motion = shot.motion.lower()

    # Triggers are surface substrings matched with ``in``. Two rules keep that
    # cheap check honest: (1) inflected forms are listed explicitly rather than
    # stemmed, so "defies"/"defying" match (bare "defy" is not a substring of
    # them); (2) words that embed in unrelated host words are tightened into
    # phrases, so they fire on the real signal only — "grows into"/"grows from"
    # (transformation) does not match "camera grows closer" (a move), and
    # "speaks"/"says" (dialogue) do not match "voiceover".
    impossible_words = ["edges stay", "impossible", "defy", "defies", "defying", "no-drain"]
    fluid_words = ["water", "drain", "liquid", "fluid"]
    transformation_words = ["melt", "morph", "transform", "grows into", "grows from"]
    dialogue_words = ["speaks", "says", "dialogue"]

    if any(word in motion for word in impossible_words):
        return "impossible_physics"
    elif any(word in motion for word in fluid_words):
        return "fluid_motion"
    elif any(word in motion for word in transformation_words):
        return "transformation"
    elif any(word in motion for word in dialogue_words):
        return "dialogue"
    return "default"
