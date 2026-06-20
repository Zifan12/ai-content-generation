from src.generation.render_adapters.router import pick_model, classify_motion
from src.schemas.generation import Shot
from src.generation.render_adapters.rules import RenderRules

def test_router():
    shot = Shot(motion="water drains inward, edges stay full")
    rules = RenderRules()

    assert pick_model("impossible_physics", rules) == "minimax_hailuo"
    assert pick_model("impossible_physics", rules, available={"veo3_1"}) == "veo3_1"
    assert classify_motion(shot, "reveal") == "impossible_physics"

