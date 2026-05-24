"""
LLM generation schemas — request/response contracts.

PIPELINE ROLE:
  Prompt engine → ScriptRequest → LLM → ScriptPackage (this file) → Post to TikTok

WHY THIS FILE EXISTS:
  Type-safe request/response schema for script generation. ScriptRequest carries
  context (topic, viral examples, tone). ScriptPackage is the LLM's structured
  output (hook, body, CTA, hashtags, thumbnail prompt). Few-shot examples in
  model_config guide LLM output format and tone.
"""

from pydantic import BaseModel, Field
from typing import Optional

class ScriptRequest(BaseModel):
    """
    Input contract for TikTok script generation.
    
    Attributes:
      topic: what the video is about (e.g., "organizing your closet")
      viral_examples: hook lines from top-performing videos (few-shot conditioning)
      tone: desired voice ("educational", "entertaining", "motivational", etc.)
      target_duration_seconds: video length constraint (affects content density)
    """
    topic: str = Field(description="What the video is about")
    viral_examples: list[str] = Field(description="Hook lines from top-performing videos on this topic")
    tone: str = Field(description="Tone of the script, e.g. educational, entertaining, motivational")
    target_duration_seconds: int = Field(description="Target video length in seconds")


class ScriptPackage(BaseModel):
    """
    Full script package — LLM output for content generation.
    
    Attributes:
      hook: attention-grabbing opening (1-2 seconds of screen time)
      body: main content delivery (builds on hook, develops idea)
      cta: call-to-action (encourages share/comment/follow)
      hashtags: list of platform tags (for discoverability)
      thumbnail_prompt: image generation prompt for video cover
    
    Model Config (model_config):
      Includes few-shot examples to guide LLM on format, tone, and content density.
      Examples flow into JSON schema served to LLM, acting as implicit instruction.
    """
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
    