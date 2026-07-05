"""Deterministic per-shot model routing + consistency grouping (plan Task 3).

This is the code seam between the writer's two LLM calls (spec 2026-07-04 §2.2):
call 1 classifies each shot with a MotionTag; THIS module decides which model
renders it (never the LLM — routing is an evidence-locked table, and a table in
code can be asserted while a table in prompt-space can only be hoped about); call 2
then converts each shot's motion intent into the routed model's dialect.

Routing reads config/render_rules.yaml through RenderRules — the audit-issue-10
fix: `rules.route()` gains its production call site here.

Grouping rules v1 (flagged for user ratification in the plan — the WHY of each):

  IDENTICAL character sets, not pairwise overlap.
    A group renders as ONE multi-shot generation seeded by ONE grounded still — the
    first shot's frame. A character who first appears mid-group has no presence in
    that seed still and would render UNGROUNDED (the BUG-002 wrong-face/wrong-outfit
    failure class). Requiring every member shot to carry exactly the same cast
    guarantees the seed still grounds every face the generation will draw. Pairwise
    overlap (A+B share Eve, B+C share Adam) is the relaxation to revisit once
    @-reference / Elements support is verified on the Higgsfield CLI.

  Hard yaml caps only (ratings.max_shots / ratings.max_seconds).
    The ~10s soft consistency preference (doc 18 + 2026-07-04 spike) lives in the
    writer's duration budgeting, not here: splitting a group at 10s can strand a
    one-shot tail, and a singleton group means an independently generated still —
    re-introducing exactly the drift the grouping exists to avoid.

  Only multi-shot-capable models merge.
    Capability = the model block HAS a ratings.max_shots entry. Read from the yaml,
    never from a hardcoded model name, so a future consistency model (Seedance 2.5
    etc.) slots in as config only (swappable-leaf principle).
"""

from pydantic import BaseModel, ConfigDict

from src.generation.render_adapters.rules import RenderRules
from src.schemas.generation import MotionTag, ShotDraft


class RoutingDecision(BaseModel):
    """One shot's routing outcome, self-documenting (OpenMontage selector pattern).

    Attributes:
      shot_index: Position of the shot in the draft list (and final package).
      motion_tag: The writer's shot-content classification this decision consumed.
      model_cli_id: The chosen Higgsfield model — first-ranked entry for the tag in
        config/render_rules.yaml's routing table.
      reason: Human-readable one-liner of why this model won, for logs and eval.
    """

    model_config = ConfigDict(extra="forbid")

    shot_index: int
    motion_tag: MotionTag
    model_cli_id: str
    reason: str


def route_shots(drafts: list[ShotDraft], rules: RenderRules) -> list[RoutingDecision]:
    """Assign each draft shot the first-ranked model for its motion_tag.

    Pure table lookup — `rules.route(tag)` returns the yaml's ranked cli_id list
    and the first entry wins. Returns one RoutingDecision per draft, in order.
    Raises nothing of its own: every MotionTag value is a yaml routing key by
    construction (enum parity is enforced by test), and unknown tags fall through
    to the yaml's default route inside `rules.route`.
    """
    decisions: list[RoutingDecision] = []
    for index, draft in enumerate(drafts):
        ranked = rules.route(draft.motion_tag.value)
        decisions.append(
            RoutingDecision(
                shot_index=index,
                motion_tag=draft.motion_tag,
                model_cli_id=ranked[0],
                reason=(
                    f"tag={draft.motion_tag.value} -> {ranked[0]} "
                    f"(first of ranked {ranked} per render_rules.yaml routing)"
                ),
            )
        )
    return decisions


def _supports_multi_shot(model_cli_id: str, rules: RenderRules) -> bool:
    """A model can host a multi-shot group iff its yaml block rates max_shots."""
    return "max_shots" in rules.data["models"][model_cli_id]["ratings"]


def consistency_groups(
    drafts: list[ShotDraft],
    decisions: list[RoutingDecision],
    rules: RenderRules,
) -> list[list[int]]:
    """Partition shot indices into render groups, preserving shot order.

    Each returned inner list is rendered as ONE generation: multi-member groups
    become a single multi-shot job on that model (one grounded seed still, internal
    cuts); singletons render as independent still + i2v.

    A shot JOINS the current group only if ALL hold (module docstring has the why):
      - routed to the same model as the group, and that model supports multi-shot
        (has a ratings.max_shots entry in the yaml);
      - characters_in_frame is the IDENTICAL set as the group's (order-insensitive);
      - the group stays within the model's ratings.max_shots; and
      - summed duration stays within the model's ratings.max_seconds.

    Every shot appears in exactly one group; group order and intra-group order both
    follow shot order.
    """
    groups: list[list[int]] = []
    current: list[int] = []
    current_model: str | None = None
    current_cast: frozenset[str] = frozenset()
    current_seconds = 0

    def _close() -> None:
        nonlocal current
        if current:
            groups.append(current)
            current = []

    for draft, decision in zip(drafts, decisions):
        model = decision.model_cli_id
        cast = frozenset(draft.characters_in_frame)

        if not _supports_multi_shot(model, rules):
            _close()
            groups.append([decision.shot_index])
            current_model = None
            continue

        fits_running_group = (
            current
            and model == current_model
            and cast == current_cast
            and len(current) < rules.max_shots(model)
            and current_seconds + draft.duration_seconds <= rules.max_seconds(model)
        )
        if fits_running_group:
            current.append(decision.shot_index)
            current_seconds += draft.duration_seconds
        else:
            _close()
            current = [decision.shot_index]
            current_model = model
            current_cast = cast
            current_seconds = draft.duration_seconds

    _close()
    return groups
