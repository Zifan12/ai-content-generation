"""
Tests for src/reference/frame_judge.py — offline via a FakeLLM that captures the
call. No real vision model, no network. Verifies the frame path is forwarded on
the images= seat, the character/hint land in the prompt, the max_tokens override
is passed, and the verdict passes through unchanged.
"""

from pathlib import Path

from src.monitor.schemas import CharacterRef
from src.reference.frame_judge import FrameJudge
from src.reference.schemas import FrameVerdict


class FakeLLM:
    def __init__(self, verdict: FrameVerdict) -> None:
        self._verdict = verdict
        self.prompt: str | None = None
        self.images: list[str] | None = None
        self.max_tokens: int | None = None

    def parse(self, prompt: str, response_model: type, **kwargs) -> FrameVerdict:
        self.prompt = prompt
        self.images = kwargs.get("images")
        self.max_tokens = kwargs.get("max_tokens")
        return self._verdict


def _verdict() -> FrameVerdict:
    return FrameVerdict(
        character_present=True,
        face_visibility="clear",
        text_or_watermark_overlap=False,
        angle="front",
        single_character=True,
        usable=True,
        reason="Eve front-facing, face clear, no overlay.",
    )


def _character() -> CharacterRef:
    return CharacterRef(name="Eve", ip_source="Stellar Blade")


def test_judge_forwards_frame_on_images_seat():
    fake = FakeLLM(verdict=_verdict())
    judge = FrameJudge(llm=fake)

    frame_path = Path("frames/frame_0003.png")
    judge.judge(frame_path, _character(), appearance_hint=None)

    assert fake.images == [str(frame_path)]


def test_judge_prompt_carries_character_and_hint():
    fake = FakeLLM(verdict=_verdict())
    judge = FrameJudge(llm=fake)

    judge.judge(
        Path("f.png"), _character(), appearance_hint="short white hair, black bodysuit"
    )

    assert fake.prompt is not None
    assert "Eve" in fake.prompt
    assert "Stellar Blade" in fake.prompt
    assert "short white hair, black bodysuit" in fake.prompt


def test_judge_omits_hint_block_when_none():
    fake = FakeLLM(verdict=_verdict())
    judge = FrameJudge(llm=fake)

    judge.judge(Path("f.png"), _character(), appearance_hint=None)

    assert fake.prompt is not None
    assert "appearance_hint" not in fake.prompt


def test_judge_uses_max_tokens_override_above_shared_default():
    fake = FakeLLM(verdict=_verdict())
    judge = FrameJudge(llm=fake)

    judge.judge(Path("f.png"), _character(), appearance_hint=None)

    assert fake.max_tokens is not None
    assert fake.max_tokens > 1024


def test_judge_passes_verdict_through_unchanged():
    expected = _verdict()
    fake = FakeLLM(verdict=expected)
    judge = FrameJudge(llm=fake)

    result = judge.judge(Path("f.png"), _character(), appearance_hint=None)

    assert result == expected
