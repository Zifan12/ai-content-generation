"""Tests for POVPitcher (src/generation/pov/pitcher.py, ticket 05).

Mirrors tests/generation/pov/test_script_writer.py's FakeLLM idiom (this
repo's exemplar): pin the structured-output call contract (response_model,
system prompt, max_tokens override) and that the system prompt actually
teaches the field spec / craft rules the PRD names (judgeable-in-seconds,
distinct pitches, one continuous moment, first-person native).
"""

from src.generation.pov.pitcher import POV_PITCHER_SYSTEM_PROMPT, POVPitcher
from src.generation.pov.schemas import POVPitch, POVPitchSlate


def _slate() -> POVPitchSlate:
    return POVPitchSlate(
        pitches=[
            POVPitch(
                who="a cave explorer",
                where="a crystal cavern",
                what_happens="the explorer reaches for a glowing shard",
                turn="the cavern is not empty after all",
            ),
            POVPitch(
                who="a diver",
                where="a sunken WWII wreck",
                what_happens="the diver sweeps silt from a cabin door",
                turn="a still-ticking pocket watch is wedged in the hinge",
            ),
            POVPitch(
                who="a night-shift mechanic",
                where="an abandoned observatory dome",
                what_happens="the mechanic climbs toward a jammed telescope mount",
                turn="the dome slit is already open",
            ),
        ]
    )


class FakeLLM:
    def __init__(self, result: object) -> None:
        self._result = result

    def parse(self, prompt: str, response_model: type, **kwargs: object) -> object:
        self.prompt = prompt
        self.response_model = response_model
        self.system = kwargs.get("system")
        self.max_tokens = kwargs.get("max_tokens")
        return self._result


def test_pitch_calls_llm_with_pov_pitch_slate_response_model() -> None:
    llm = FakeLLM(_slate())
    pitcher = POVPitcher(llm=llm)

    result = pitcher.pitch("deep sea")

    assert result is llm._result
    assert llm.response_model is POVPitchSlate
    assert llm.system == POV_PITCHER_SYSTEM_PROMPT
    assert isinstance(llm.max_tokens, int) and llm.max_tokens > 0


def test_pitch_injects_topic_as_tagged_data() -> None:
    llm = FakeLLM(_slate())
    pitcher = POVPitcher(llm=llm)

    pitcher.pitch("deep sea")

    assert "<topic>" in llm.prompt
    assert "deep sea" in llm.prompt


def test_prompt_teaches_the_four_pitch_fields() -> None:
    llm = FakeLLM(_slate())
    pitcher = POVPitcher(llm=llm)

    pitcher.pitch("deep sea")

    assert "who" in llm.system
    assert "where" in llm.system
    assert "what_happens" in llm.system
    assert "turn" in llm.system


def test_prompt_teaches_judgeable_in_seconds_and_distinct_pitches() -> None:
    llm = FakeLLM(_slate())
    pitcher = POVPitcher(llm=llm)

    pitcher.pitch("deep sea")

    assert "JUDGEABLE IN SECONDS" in llm.system
    assert "DISTINCT PITCHES" in llm.system


def test_prompt_teaches_one_continuous_moment_and_first_person_native() -> None:
    llm = FakeLLM(_slate())
    pitcher = POVPitcher(llm=llm)

    pitcher.pitch("deep sea")

    assert "ONE CONTINUOUS MOMENT" in llm.system
    assert "FIRST-PERSON NATIVE" in llm.system


def test_prompt_names_the_slate_size_and_no_staging() -> None:
    llm = FakeLLM(_slate())
    pitcher = POVPitcher(llm=llm)

    pitcher.pitch("deep sea")

    assert "3-5" in llm.system
    assert "do not write any of that" in llm.system.lower() or "downstream" in llm.system.lower()
