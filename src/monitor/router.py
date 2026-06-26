from src.providers.llm.anthropic_llm import AnthropicLLM
from src.monitor.schemas import AnglePitch, RenderBackend, RoutingDecision


class FormatRouter:
    """
    Maps an approved angle's wished-for render backend onto a backend that is
    actually available in this deployment.

    In v1 only ``visual_satire`` is a built backend, so any angle that wishes
    for an unbuilt backend is substituted down to ``visual_satire`` (the single
    hardcoded fallback). Routing is a deterministic dictionary lookup; the
    ``llm`` is carried for symmetry with the other monitor agents and possible
    future smart-routing, but is never called in v1.
    """

    def __init__(self, llm: AnthropicLLM | None, available_backends: dict[str, bool]):
        self.llm = llm
        self.available_backends = available_backends

    def route(self, angle: AnglePitch) -> RoutingDecision:
        """
        Resolve the angle's wished-for backend against what is available.

        Returns a RoutingDecision whose ``backend`` is the wished-for backend
        when it is available, or ``visual_satire`` when it is not. A backend
        absent from ``available_backends`` is treated as unavailable rather than
        raising. ``is_substitute`` flags whether a swap occurred, and
        ``substitution_note`` explains it (empty string when no swap happened).
        """
        wished_backend = angle.render_backend

        if self.available_backends.get(wished_backend, False):
            return RoutingDecision(
                backend=wished_backend,
                is_substitute=False,
                substitution_note="",
            )

        return RoutingDecision(
            backend=RenderBackend.visual_satire,
            is_substitute=True,
            substitution_note=(
                f"Wished-for backend '{wished_backend.value}' is not available; "
                f"substituted '{RenderBackend.visual_satire.value}'."
            ),
        )
