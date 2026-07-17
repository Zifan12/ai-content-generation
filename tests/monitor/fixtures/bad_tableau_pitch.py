"""Negative-control fixture: a schema-VALID but craft-DEAD StoryPitch.

The whole point of this fixture is to prove that the ``StoryCraftGate`` LLM
judge — not the Pydantic schema — is what rejects a bad pitch.  Every field
here is deliberately constructed to satisfy every ``StoryPitch`` /
``StoryBeat`` validator (3-6 beats, framing variety, at most one hero moment)
while still being a story with nothing underneath it:

- **No visible turn.** All three beats are the same static tableau of
  Homelander standing on a rooftop; nothing on screen ever changes state.
  The denied thing (the rampage) never begins to happen.
- **Unearned payoff.** The "reveal" beat could be the first frame — there is
  no build the payoff pays off.
- **Emotion labeled, not shown.** The narration announces "furious",
  "betrayed", "rage" instead of letting a physical action carry the feeling.

A good judge should therefore return ``visible_turn=False``,
``earned_payoff=False``, ``emotion_physical_tell=False`` and
``would_watch=False`` → ``passes`` is False.  If the schema ever changes such
that this fixture no longer constructs, the ``import`` here fails loudly and
the guard test in ``test_story_craft_gate.py`` catches the rot.

Used by:
- ``tests/monitor/test_story_craft_gate.py`` (FakeLLM guard: proves the
  fixture still validates).
- ``tests/monitor/test_story_craft_gate_live.py`` (Task 8, real LLM: the gate
  must score this ``passes=False`` — the writer-judge "everything scores 5.00"
  lesson made executable).
"""

from src.monitor.schemas import (
    BeatRole,
    CharacterRef,
    ContentMode,
    ShotSize,
    StoryBeat,
    StoryPitch,
)

BAD_TABLEAU_PITCH = StoryPitch(
    logline="Homelander stands on a rooftop looking angry about the finale.",
    mode=ContentMode.wish,
    characters=[
        CharacterRef(
            name="Homelander",
            ip_source="The Boys",
            needs_reference=True,
        )
    ],
    desired_moment=(
        "Fans wanted to finally see Homelander cut loose in the full violent "
        "rampage the finale teased and never delivered."
    ),
    beats=[
        StoryBeat(
            role=BeatRole.establish,
            visual_line=(
                "Homelander stands motionless on a rooftop at dusk, cape hanging "
                "still, city lights behind him."
            ),
            narration_line="Homelander is furious about how the finale ended.",
            shot_size=ShotSize.establishing,
            characters_in_frame=["Homelander"],
            hero_moment=False,
        ),
        StoryBeat(
            role=BeatRole.establish,
            visual_line=(
                "The same rooftop, the same still pose, framed a little closer; "
                "nothing has moved."
            ),
            narration_line="He feels betrayed and wants everyone to pay.",
            shot_size=ShotSize.medium,
            characters_in_frame=["Homelander"],
            hero_moment=False,
        ),
        StoryBeat(
            role=BeatRole.reveal,
            visual_line=(
                "Tight on Homelander's face, still standing on the same rooftop, "
                "eyes forward."
            ),
            narration_line="Now the whole world will finally see his true rage.",
            shot_size=ShotSize.close_up,
            characters_in_frame=["Homelander"],
            hero_moment=False,
        ),
    ],
    why_it_lands="Homelander is a popular character and fans are angry.",
    legal_flag=True,
)
