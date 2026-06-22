from src.generation.render_adapters.rules import RenderRules


def test_rules():
    rules = RenderRules()

    assert rules.route("impossible_physics") == ["minimax_hailuo", "seedance_2_0", "veo3_1"]
    assert rules.route("unknown_tag") == ["veo3_1", "kling3_0"]
    assert rules.model("veo3_1")["ratings"]["max_seconds"] == 8
    assert rules.max_seconds("veo3_1") == 8

    # global_constraints now requires the prompt kind; a still prompt should still
    # carry the always-append baseline (locked-camera line lives in every kind).
    still = rules.global_constraints(kind="still", style="whatever")
    assert any("locked camera" in c for c in still)


def test_global_constraints_substitutes_style_and_scopes_by_kind():
    """global_constraints fills the [STYLE] placeholder and returns the right per-kind subset.

    Three behaviours are pinned, all reading the REAL committed yaml:

      1. [STYLE] substitution — the style_consistency rule holds a literal
         "[STYLE]" placeholder; passing ``style=`` must replace it. We use a
         nonsense sentinel ("zzqmood") so a match can't be coincidental: it must
         appear in the returned constraints, and the literal "[STYLE]" must NOT
         survive.
      2. Kind scoping (still) — style_consistency is ``kinds: [still]`` (the i2v
         rule: the motion prompt must not restate the still's look), so the
         still subset DOES include the no-style-drift line.
      3. Kind scoping (motion) — the motion subset must NOT include the
         style-consistency line, and (since the still is a silent image) must
         not need a style value to be well-formed.

    Assertions inspect the returned list with ``any(substring in element ...)``
    because each constraint is a full sentence and the sentinel/marker is a
    substring inside one element, not a standalone list item.
    """
    rules = RenderRules()

    still = rules.global_constraints(kind="still", style="zzqmood")
    # 1. the sentinel was substituted into the [STYLE] blank ...
    assert any("zzqmood" in c for c in still)
    # ... and no raw placeholder leaked through.
    assert not any("[STYLE]" in c for c in still)
    # 2. still keeps the style-consistency line.
    assert any("no style drift" in c for c in still)

    motion = rules.global_constraints(kind="motion", style="zzqmood")
    # 3. motion drops the style-consistency line entirely (i2v: don't restate the look).
    assert not any("no style drift" in c for c in motion)