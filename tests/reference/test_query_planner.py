from src.monitor.schemas import (
    BeatRole,
    CaptionPolicy,
    CharacterRef,
    ContentMode,
    ShotSize,
    StoryBeat,
    StoryPitch,
)
from src.reference.query_planner import QueryPlanner
from src.reference.schemas import QueryPlan

SAMPLE_CHARACTER = CharacterRef(name="Eve", ip_source="Stellar Blade")


def _beat(role: BeatRole, shot_size: ShotSize, hero: bool = False) -> StoryBeat:
    return StoryBeat(
        role=role,
        visual_line="x",
        narration_line=None,
        shot_size=shot_size,
        characters_in_frame=["Eve"],
        hero_moment=hero,
    )


SAMPLE_PITCH = StoryPitch(
    logline="Eve refuses to yield in the fight fans were denied",
    mode=ContentMode.wish,
    characters=[SAMPLE_CHARACTER],
    desired_moment="Eve landing the finishing blow the trailer cut away from",
    beats=[
        _beat(BeatRole.hook, ShotSize.wide),
        _beat(BeatRole.turn, ShotSize.medium),
        _beat(BeatRole.payoff, ShotSize.close_up, hero=True),
    ],
    caption_policy=CaptionPolicy.hook_only,
    hook_line="the ending they owed us",
    why_it_lands="x",
    legal_flag=False,
)


class FakeLLM:
    def __init__(self, plan: QueryPlan) -> None:
        self._plan = plan
        self.prompt: str | None = None
        self.max_tokens: int | None = None

    def parse(self, prompt: str, response_model: type, **kwargs) -> QueryPlan:
        self.prompt = prompt
        self.max_tokens = kwargs.get("max_tokens")
        return self._plan


def _sample_plan() -> QueryPlan:
    return QueryPlan(
        queries=["Stellar Blade Eve trailer", "Stellar Blade Eve boss fight"],
        target_description="Eve, front-facing, mid-combat stance",
    )


def test_plan_returns_query_plan_and_prompt_carries_character_and_context():
    fake = FakeLLM(plan=_sample_plan())
    planner = QueryPlanner(llm=fake)

    result = planner.plan(
        SAMPLE_CHARACTER, SAMPLE_PITCH, context_block="<context>\nsummary: x\n</context>"
    )

    assert result == _sample_plan()
    assert fake.prompt is not None
    assert "Eve" in fake.prompt
    assert "Stellar Blade" in fake.prompt
    assert SAMPLE_PITCH.logline in fake.prompt
    assert SAMPLE_PITCH.desired_moment in fake.prompt
    assert "<context>" in fake.prompt


def test_plan_with_empty_context_block_has_no_context_tag():
    fake = FakeLLM(plan=_sample_plan())
    planner = QueryPlanner(llm=fake)

    planner.plan(SAMPLE_CHARACTER, SAMPLE_PITCH, context_block="")

    assert "<context>" not in fake.prompt


def test_plan_uses_max_tokens_override_above_shared_default():
    fake = FakeLLM(plan=_sample_plan())
    planner = QueryPlanner(llm=fake)

    planner.plan(SAMPLE_CHARACTER, SAMPLE_PITCH, context_block="")

    assert fake.max_tokens is not None
    assert fake.max_tokens > 1024
