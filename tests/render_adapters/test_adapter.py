from src.generation.render_adapters.schemas import RenderJob


def test_pydantic_model():
    still_render = RenderJob(
        model_cli_id="nano_banana_2",
        kind="still",
        prompt="test",
        image_ref=None,
        start_image=None,
        end_image=None,
        duration=None,
        aspect_ratio="9:16",
        shot_index=0
    )

    assert still_render.model_dump() == {
        "model_cli_id": "nano_banana_2",
        "kind": "still",
        "prompt": "test",
        "image_ref": None,
        "start_image": None,
        "end_image": None,
        "duration": None,
        "aspect_ratio": "9:16",
        "shot_index": 0,
    }