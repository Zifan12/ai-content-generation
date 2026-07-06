from src.reference.schemas import VideoCandidate, VideoPick
from src.reference.video_finder import VideoPicker

SAMPLE_CANDIDATES = [
    VideoCandidate(
        video_id="abc123",
        url="https://youtube.com/watch?v=abc123",
        title="Stellar Blade Eve Official Trailer",
        channel="PlayStation",
        duration_seconds=90.0,
        view_count=500000,
        description="Official reveal trailer.",
        transcript_excerpt="Eve draws her blade and leaps into battle.",
    ),
    VideoCandidate(
        video_id="def456",
        url="https://youtube.com/watch?v=def456",
        title="Stellar Blade Eve Reaction",
        channel="SomeReactor",
        duration_seconds=600.0,
        view_count=20000,
        description="My reaction to the trailer!",
        transcript_excerpt="Oh my god look at that!",
    ),
]


class FakeLLM:
    def __init__(self, pick: VideoPick) -> None:
        self._pick = pick
        self.prompt: str | None = None
        self.max_tokens: int | None = None

    def parse(self, prompt: str, response_model: type, **kwargs) -> VideoPick:
        self.prompt = prompt
        self.max_tokens = kwargs.get("max_tokens")
        return self._pick


def _sample_pick() -> VideoPick:
    return VideoPick(chosen_video_ids=["abc123"], reason="Official upload, clear footage")


def test_pick_returns_video_pick_and_prompt_carries_candidate_data():
    fake = FakeLLM(pick=_sample_pick())
    picker = VideoPicker(llm=fake)

    result = picker.pick(SAMPLE_CANDIDATES, target_description="Eve, front-facing, mid-combat")

    assert result == _sample_pick()
    assert fake.prompt is not None
    assert "Stellar Blade Eve Official Trailer" in fake.prompt
    assert "PlayStation" in fake.prompt
    assert "Eve draws her blade" in fake.prompt
    assert "Stellar Blade Eve Reaction" in fake.prompt
    assert "Eve, front-facing, mid-combat" in fake.prompt


def test_pick_uses_max_tokens_override_above_shared_default():
    fake = FakeLLM(pick=_sample_pick())
    picker = VideoPicker(llm=fake)

    picker.pick(SAMPLE_CANDIDATES, target_description="x")

    assert fake.max_tokens is not None
    assert fake.max_tokens > 1024
