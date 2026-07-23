"""Seam-2 pure-function tests for the POV verdict module (slice ③).

.scratch/pov-slice3/PRD.md Testing Decisions, seam 2: each helper is a
deterministic input→output function — prompt hashing, taxonomy loading,
prediction-block derivation, final-command derivation. No LLM, no network,
no paid render; the one file-reading fixture (RenderRules) reads the
committed yaml exactly like the sibling compiler/render-sheet tests do.
"""

import pytest

from src.generation.pov.verdict import (
    build_prediction_block,
    derive_final_command,
    prompt_hash,
)
from src.generation.render_adapters.rules import RenderRules

_GUARDS = {"code_check", "prompt_rule", "watch_only"}
_APPLIES = {"always", "refs_only"}
_TAGS = {"objective", "taste"}


@pytest.fixture(scope="module")
def rules() -> RenderRules:
    return RenderRules()


# --- prompt hashing ---------------------------------------------------------


def test_prompt_hash_is_stable_and_content_keyed() -> None:
    """Same prompt text → same hash (the probe-exemption key must survive a
    process restart); different text → different hash."""
    a = prompt_hash("Camera IS the eyes. Subject: an unseen diver.")
    b = prompt_hash("Camera IS the eyes. Subject: an unseen diver.")
    c = prompt_hash("Camera IS the eyes. Subject: an unseen explorer.")

    assert a == b
    assert a != c
    # Filesystem/log-friendly: short lowercase hex, no separators.
    assert a.isalnum() and a == a.lower()


# --- defect taxonomy (config contract) --------------------------------------


def test_defect_taxonomy_entries_carry_the_full_contract(rules: RenderRules) -> None:
    """Every taxonomy entry names its guard status honestly (code_check /
    prompt_rule / watch_only), its applicability, a default tag, and an
    evidence tag — PRD user stories 3, 5, 8, 26."""
    taxonomy = rules.pov_verdict()["defect_taxonomy"]

    assert len(taxonomy) >= 10  # the audit found at least this many classes
    for slug, entry in taxonomy.items():
        assert slug == slug.lower().replace(" ", "_"), slug
        assert entry["guard"] in _GUARDS, slug
        assert entry["applies"] in _APPLIES, slug
        assert entry["default_tag"] in _TAGS, slug
        assert entry["description"], slug
        assert entry["evidence"], slug


def test_taxonomy_covers_the_watched_failure_record(rules: RenderRules) -> None:
    """The audited POV-era defects (watch checklist + BUG-033→040 + the banked
    explosion-bind observation) each have a countable class."""
    taxonomy = rules.pov_verdict()["defect_taxonomy"]

    for expected in [
        "money_shot_missed",
        "angle_switch",
        "body_leak",
        "beat_teleport",
        "text_leak",
        "wrong_scale",
        "unended_effect",
        "camera_scale_mismatch",
        "target_no_end_state",
        "wrong_pose",
        "effect_detached",
        "identity_mismatch",
    ]:
        assert expected in taxonomy, expected


def test_open_unguarded_defects_are_marked_watch_only(rules: RenderRules) -> None:
    """BUG-037 (no corpus-backed fix) and the count-1 explosion-bind class must
    not claim a guard they don't have — the PRD's honesty rule (user story 3)."""
    taxonomy = rules.pov_verdict()["defect_taxonomy"]

    assert taxonomy["camera_scale_mismatch"]["guard"] == "watch_only"
    assert taxonomy["effect_detached"]["guard"] == "watch_only"


def test_spending_brakes_are_the_ratified_values(rules: RenderRules) -> None:
    """D2 grilling 2026-07-23: cap 150->300 (fits the native-1080p ladder:
    probe 45 + stills + 135cr final; second take stays an override).
    Staged-director D7 (2 retakes) unchanged."""
    brakes = rules.pov_verdict()["spending_brakes"]

    assert brakes["per_story_credit_cap"] == 300
    assert brakes["max_failed_retakes"] == 2


def test_still_generation_cost_is_the_measured_rate(rules: RenderRules) -> None:
    """Ticket 01: the rate table carries the measured GPT Image 2 still cost
    (2 stills x 7cr, 2026-07-22) so the spend tally never invents a rate
    (ADR-0007)."""
    assert rules.pov_verdict()["still_generation_credits"] == 7.0


# --- prediction block -------------------------------------------------------


def test_prediction_block_states_guarded_expectations(rules: RenderRules) -> None:
    """Deming consult: the ruleset states its own theory before the watch.
    Guarded classes appear as expectations; unguarded (watch_only) classes are
    flagged as open risks, never claimed as guarded."""
    block = build_prediction_block(rules, has_refs=False)

    # A guarded, always-on class reads as an expectation.
    assert "angle_switch" in block
    # An open defect is flagged unguarded, not promised.
    assert "camera_scale_mismatch" in block
    assert "UNGUARDED" in block
    guarded_part = block[: block.index("UNGUARDED")]
    assert "camera_scale_mismatch" not in guarded_part


def test_prediction_block_includes_ref_classes_only_with_refs(rules: RenderRules) -> None:
    without = build_prediction_block(rules, has_refs=False)
    with_refs = build_prediction_block(rules, has_refs=True)

    assert "identity_mismatch" not in without
    assert "identity_mismatch" in with_refs


def test_prediction_block_is_deterministic(rules: RenderRules) -> None:
    assert build_prediction_block(rules, has_refs=True) == build_prediction_block(
        rules, has_refs=True
    )


# --- final-command derivation ----------------------------------------------


def test_final_command_swaps_resolution_and_restates_cost(rules: RenderRules) -> None:
    """The released final is the SAME prompt at the configured final
    resolution, with a fresh cost line from the measured rate table (L7:
    never emit a command without stating its cost)."""
    sanity_cmd = (
        'higgsfield generate create seedance_2_0 --prompt "a test prompt" '
        "--aspect_ratio 9:16 --duration 15 --resolution 480p --wait"
    )

    command, cost_line = derive_final_command(sanity_cmd, duration_seconds=15, rules=rules)

    # Finals are native 1080p x1 (blur lesson 2026-07-22: upscaled probes are
    # never keepers; ticket 01).
    assert "--resolution 1080p" in command
    assert "480p" not in command
    assert command.replace("--resolution 1080p", "--resolution 480p") == sanity_cmd
    # 15s × 9.0cr/s (measured 2026-07-22, two refunded attempts) = 135cr
    assert "135" in cost_line
    assert "1080p" in cost_line


# --- hash over prompt + refs (D2 ticket 05) ----------------------------------


def test_hash_without_refs_matches_the_pre_d2_form() -> None:
    """Text-only hashes must stay byte-identical so every pre-D2 log record
    (incl. retro seeds) keeps matching without migration."""
    import hashlib

    text = "a compiled prompt"
    assert prompt_hash(text) == hashlib.sha256(text.encode()).hexdigest()[:16]
    assert prompt_hash(text, ()) == prompt_hash(text)


def test_hash_changes_when_a_ref_is_swapped_and_ignores_path_prefix() -> None:
    text = "a compiled prompt"
    with_a = prompt_hash(text, ["C:/abs/refs/hell_city/keeper_a.png"])
    with_b = prompt_hash(text, ["C:/abs/refs/hell_city/keeper_b.png"])
    relative_a = prompt_hash(text, ["refs/hell_city/keeper_a.png"])

    assert with_a != prompt_hash(text)  # refs runs never collide with text-only
    assert with_a != with_b  # ref swap = new config
    assert with_a == relative_a  # file NAME keys the hash, not the path prefix
