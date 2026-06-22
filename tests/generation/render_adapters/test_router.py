import pytest

from src.generation.render_adapters.router import pick_model, classify_motion
from src.schemas.generation import Shot
from src.generation.render_adapters.rules import RenderRules

def test_router():
    shot = Shot(motion="water drains inward, edges stay full")
    rules = RenderRules()

    assert pick_model("impossible_physics", rules) == "minimax_hailuo"
    assert pick_model("impossible_physics", rules, available={"veo3_1"}) == "veo3_1"
    assert classify_motion(shot, "reveal") == "impossible_physics"


def test_pick_model_raises_when_no_routed_model_available():
    # available excludes every model routed for "dialogue"
    # ([veo3_1, wan2_7, kling3_0]) -> no renderable choice -> loud failure
    # rather than a None that breaks downstream.
    rules = RenderRules()
    with pytest.raises(ValueError):
        pick_model("dialogue", rules, available={"minimax_hailuo"})


def test_classify_motion_keyword_edges():
    # False-negative fix: "defies" must match impossible_physics even though
    # the bare trigger is "defy" (defy is not a substring of defies).
    assert classify_motion(Shot(motion="gravity defies all logic"), "reveal") == "impossible_physics"

    # False-positive fix: a camera move described as "grows closer" must NOT
    # trip the transformation branch (bare "grow" used to); it has no other
    # trigger, so it falls through to default.
    assert classify_motion(Shot(motion="camera grows closer toward the colossal eye"), "scale") == "default"

    # Phrase trigger still catches a real transformation.
    assert classify_motion(Shot(motion="the seed grows into a tower"), "transform") == "transformation"

