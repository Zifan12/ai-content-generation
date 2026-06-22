from scripts.archive.seeds import Seed, load_seeds


def test_load_seeds_flattens_to_pairs(tmp_path):
    yaml_text = (
        "seeds:\n"
        "  - niche: surreal_hyperreal\n"
        "    hashtags: [aisurreal, liminalai]\n"
        "  - niche: horror_ai\n"
        "    hashtags: [aihorror]\n"
    )
    p = tmp_path / "seeds.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    seeds = load_seeds(p)
    assert seeds == [
        Seed("surreal_hyperreal", "aisurreal"),
        Seed("surreal_hyperreal", "liminalai"),
        Seed("horror_ai", "aihorror"),
    ]


def test_load_seeds_filter_by_niche(tmp_path):
    yaml_text = (
        "seeds:\n"
        "  - niche: a\n"
        "    hashtags: [x, y]\n"
        "  - niche: b\n"
        "    hashtags: [z]\n"
    )
    p = tmp_path / "seeds.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    seeds = load_seeds(p, niche="b")
    assert seeds == [Seed("b", "z")]
