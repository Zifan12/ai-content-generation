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
    """Grill Q1 (150cr cap confirmed) + staged-director D7 (2 retakes)."""
    brakes = rules.pov_verdict()["spending_brakes"]

    assert brakes["per_story_credit_cap"] == 150
    assert brakes["max_failed_retakes"] == 2


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

    assert "--resolution 720p" in command
    assert "480p" not in command
    assert command.replace("--resolution 720p", "--resolution 480p") == sanity_cmd
    # 15s × 4.5cr/s (measured 2026-07-06) = 67.5cr
    assert "67.5" in cost_line
    assert "720p" in cost_line
