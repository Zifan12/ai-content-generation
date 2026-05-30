
import pytest 

from pydantic import ValidationError
from src.schemas.generation import ContentPackage

def test_content_package_validates_minimal():
    package = ContentPackage(
        video_prompt="test",
        onscreen_text=["test", "test", "test"],
        caption="test123",
        hashtags=["test1", "test2"],
        
    )

    assert package.grounding_hit_ids == []
    assert package.voiceover is None
    assert package.rationale is None

def test_content_package_rejects_missing_video_prompt():
    with pytest.raises(ValidationError):
        package = ContentPackage(
        onscreen_text=["test", "test", "test"],
        caption="test123",
        hashtags=["test1", "test2"],
        
    )

