import pytest
from src.generation.premise_generator import MAX_TOKENS, SYSTEM_PROMPT, PremiseGenerator
from src.schemas.premise import Premise, PremiseSet


def _premise(n: int = 0) -> Premise:
    return Premise(premise=f"Schema-test premise number {n}.")


def _sample_premise_set(n) -> PremiseSet:
    return PremiseSet(premises=([_premise(i) for i in range(n)]))


class FakeLLM:
    def __init__(self, return_count=10):
        self.last_system: str | None = None
        self.last_prompt = None
        self.return_count = return_count

    def parse(self, prompt, response_model, system=None, max_tokens=4096):
        self.last_prompt = prompt
        self.last_max_tokens = max_tokens
        self.last_system = system
        return _sample_premise_set(self.return_count)


def test_generate_returns_n_premises_without_db():
    fake = FakeLLM(return_count=10)
    generator = PremiseGenerator(llm=fake)
    result = generator.generate(n=10)

    assert len(result.premises) == 10
    assert fake.last_system == SYSTEM_PROMPT
    assert fake.last_max_tokens == MAX_TOKENS
    assert isinstance(result, PremiseSet)
    assert "10" in fake.last_prompt
    assert "Winner" not in fake.last_prompt

def test_generate_raises_when_llm_returns_wrong_count():
    fake = FakeLLM(return_count=7)
    generator = PremiseGenerator(llm=fake)
    with pytest.raises(ValueError):
        generator.generate(n=10)