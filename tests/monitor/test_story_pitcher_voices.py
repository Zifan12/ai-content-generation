from unittest.mock import MagicMock

from src.monitor.schemas import GapAnalysis, StoryPitchSlate, TrendingEvent
from src.monitor.story_pitcher import StoryPitcher


def _event() -> TrendingEvent:
    return TrendingEvent(
        headline="h",
        subreddit="anime",
        url="https://example.com/x",
        reaction_sample="fans want the rematch",
        trendiness_score=0.5,
        virality_window_hours=24.0,
        raw_source_data={},
        origin="manual",
    )


def _gap() -> GapAnalysis:
    return GapAnalysis(
        dominant_emotion="awe",
        audience_want="w",
        evidence_quotes=[],
        reasoning="x",
    )


def _pitcher(llm: MagicMock) -> StoryPitcher:
    llm.parse.return_value = StoryPitchSlate.model_construct(pitches=[])
    return StoryPitcher(llm=llm, embedder=MagicMock())


def test_pitch_injects_cast_voices_into_prompt():
    llm = MagicMock()
    pitcher = _pitcher(llm)

    pitcher.pitch(
        _event(), _gap(),
        cast_voices="<cast_voices>\n### elfaria\nclipped\n</cast_voices>",
    )

    sent_prompt = llm.parse.call_args.kwargs["prompt"]
    assert "<cast_voices>" in sent_prompt
    assert "clipped" in sent_prompt


def test_pitch_without_cast_voices_omits_block():
    llm = MagicMock()
    pitcher = _pitcher(llm)

    pitcher.pitch(_event(), _gap())

    assert "<cast_voices>" not in llm.parse.call_args.kwargs["prompt"]


def test_repitch_injects_cast_voices():
    from src.monitor.schemas import (
        CaptionPolicy,
        CharacterRef,
        ShotSize,
        StoryBeat,
        StoryPitch,
    )

    failed = StoryPitch(
        logline="l", mode="wish",
        characters=[CharacterRef(name="Elfaria Albis Serfort", ip_source="Wistoria")],
        desired_moment="m", scene_setting="s",
        beats=[
            StoryBeat(role="establish", visual_line="v", narration_line=None,
                      shot_size=ShotSize.wide, characters_in_frame=["Elfaria Albis Serfort"]),
            StoryBeat(role="build", visual_line="v", narration_line=None,
                      shot_size=ShotSize.medium, characters_in_frame=["Elfaria Albis Serfort"]),
            StoryBeat(role="payoff", visual_line="v", narration_line=None,
                      shot_size=ShotSize.close_up, characters_in_frame=["Elfaria Albis Serfort"],
                      hero_moment=True),
        ],
        caption_policy=CaptionPolicy.none, hook_line=None, why_it_lands="w", legal_flag=False,
    )
    llm = MagicMock()
    llm.parse.return_value = failed
    pitcher = StoryPitcher(llm=llm, embedder=MagicMock())

    pitcher.repitch(
        _event(), _gap(), failed, "give Elfaria a line",
        cast_voices="<cast_voices>\n### elfaria_albis_serfort\nclipped\n</cast_voices>",
    )

    assert "<cast_voices>" in llm.parse.call_args.kwargs["prompt"]
