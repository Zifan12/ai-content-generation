from src.monitor.router import FormatRouter
from src.monitor.schemas import AnglePitch, RenderBackend

# Angle whose wished-for backend IS the one live backend in v1.
angle_visual = AnglePitch(
    take="The dragon finally breathes fire over Tokyo Tower at dawn",
    format_description="Single wide aerial shot, slow push-in as flame erupts",
    render_backend=RenderBackend.visual_satire,
    estimated_cost_credits=24.0,
    gap_satisfaction_rationale="Shows the fire-breath payoff fans were denied",
    legal_flag=False,
)

# Angle that wishes for a backend that is NOT built in v1.
angle_voiceover = AnglePitch(
    take="A newscaster narrates the dragon's fire breath over Tokyo",
    format_description="Mock news B-roll with voiceover commentary",
    render_backend=RenderBackend.commentary_voiceover,
    estimated_cost_credits=24.0,
    gap_satisfaction_rationale="Delivers the payoff through a news frame",
    legal_flag=False,
)

# Realistic v1 cheat-sheet: visual_satire is the one built backend, the rest are not.
available_backends = {
    RenderBackend.visual_satire: True,
    RenderBackend.commentary_voiceover: False,
}


def test_render_backend_available():
    """
    When the angle's wished-for backend is available, the router passes it
    through unchanged and does not mark it a substitution.
    """
    router = FormatRouter(llm=None, available_backends=available_backends)

    result = router.route(angle=angle_visual)

    assert result.backend == RenderBackend.visual_satire
    assert result.is_substitute is False


def test_render_backend_substitute():
    """
    When the angle's wished-for backend is NOT available, the router falls back
    to the one hardcoded rescue backend (visual_satire) and flags the swap.
    """
    router = FormatRouter(llm=None, available_backends=available_backends)

    result = router.route(angle=angle_voiceover)

    assert result.backend == RenderBackend.visual_satire
    assert result.is_substitute is True
