from pydantic import BaseModel, Field
from typing import Optional

class ScriptRequest(BaseModel):
    topic: str = Field(description="What the video is about")
    viral_examples: list[str] = Field(description="Hook lines from top-performing videos on this topic")
    tone: str = Field(description="Tone of the script, e.g. educational, entertaining, motivational")
    target_duration_seconds: int = Field(description="Target video length in seconds")


class ScriptPackage(BaseModel):
    hook: str = Field(description="Get user attention")
    body: str = Field(description="main content")
    cta: str = Field(description="call to action")
    hashtags: list[str] = Field(description="platform tags")
    thumbnail_prompt: str = Field(description="image generation prompt")

    # Examples flow into the JSON schema served to the LLM via instructor —
    # acts as few-shot conditioning for shape and tone of generated output.
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "hook": "You've been folding laundry wrong your entire life.",
                    "body": "Most people fold shirts flat, which creates creases and wastes drawer space. The ranger roll method, used by the US military, compresses the shirt into a tight bundle that stands upright.",
                    "cta": "Try it on your next shirt and drop a comment if it worked.",
                    "hashtags": ["#lifehack", "#organization", "#tips"],
                    "thumbnail_prompt": "Dramatic before/after split shot: messy overflowing drawer vs. perfectly organized drawer with rolled shirts standing upright, bright lighting"
                }
            ]
        }
    }
    