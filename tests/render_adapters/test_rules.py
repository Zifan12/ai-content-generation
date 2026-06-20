from src.generation.render_adapters.rules import RenderRules



def test_rules():
    rules = RenderRules()

    assert rules.route("impossible_physics") == ["minimax_hailuo", "seedance_2_0", "veo3_1"]
    assert rules.route("unknown_tag") == ["veo3_1", "kling3_0"]
    assert rules.model("veo3_1")["ratings"]["max_seconds"] == 8
    assert rules.global_constraints() is not None
    assert rules.max_seconds("veo3_1") == 8