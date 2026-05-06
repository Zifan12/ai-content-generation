from src.blueprints.schema import Blueprint
from src.models.trend import RawContentItem
from src.observability.tracing import traced
from src.providers.llm.anthropic_llm import AnthropicLLM


SYSTEM_PROMPT = """You are an expert short-form video analyst. Your job is to extract a structured \
Blueprint of a TikTok video's viral mechanics. You receive caption, transcript (may be missing), \
author handle, duration, view/like/comment/share counts, and hashtags.

Score the 8 mechanic floats on a 0.0–1.0 scale where 0.5 = average for the niche.

If transcript is missing or the video is music-only, lower the `confidence` field below 0.5 and \
note this in `notes`. Still output the full Blueprint — never refuse.

For format / hook_type / payoff_type, use short snake_case strings (e.g. `talking_head`, \
`stitch_reaction`, `shocking_claim`, `cliffhanger`, `twist`, `reveal`). Be consistent across \
videos. The taxonomy will be locked from your outputs in a later step."""


class BlueprintExtractor:
    """One-shot LLM extraction of a Blueprint from a RawContentItem + optional transcript.

    Builds a text envelope from video metadata, sends it to Sonnet via AnthropicLLM.parse,
    and returns a validated Blueprint Pydantic object. Does not touch the database —
    persistence is the caller's responsibility (see scripts/extract_blueprints.py).
    """

    def __init__(self, llm: AnthropicLLM | None = None):
        self.llm = llm or AnthropicLLM(model="claude-sonnet-4-6")

    @traced(name="blueprints.extract", kind="generation")
    def extract(self, item: RawContentItem, transcript_text: str | None) -> Blueprint:
        """Extract a Blueprint from a scraped video item.

        Args:
            item: RawContentItem with metadata fields populated (description, stats, etc.).
            transcript_text: Plain text transcript from subtitles, or None if unavailable.

        Returns:
            Validated Blueprint object. Confidence will be low if transcript is missing.
        """
        envelope = self._build_envelope(item, transcript_text)
        
        return self.llm.parse(
            prompt=envelope,
            response_model=Blueprint,
            system=SYSTEM_PROMPT,
            max_tokens=2048,
        )


    def _build_envelope(self, item: RawContentItem, transcript_text: str | None) -> str:
        """Build text envelope from video metadata + optional transcript for LLM input.

        Args:
            item: RawContentItem with author, duration, stats, hashtags, description.
            transcript_text: Plain text transcript, or None if unavailable.

        Returns:
            Formatted prompt string containing all video context for Blueprint extraction.
        """
        transcript_block = (
            f"Transcript:\n{transcript_text}"
            if transcript_text
            else "Transcript: (missing)"
        )

        if item.hashtags:
            hashtags = ", ".join(item.hashtags)
        else:
            hashtags = "(none)"

        return(
            f"Author: {item.author_username or '(unknown)'}\n"
            f"Duration: {item.duration_in_seconds or 'unknown'} seconds\n"
            f"Views: {item.views:,} | Likes: {item.likes:,} | "
            f"Comments: {item.comments:,} | Shares: {item.shares:,}\n"
            f"Hashtags: {hashtags}\n\n"
            f"Caption / Description: \n{item.description or '(no caption)'}\n\n"
            f"{transcript_block}\n\n"
            f"Extract the Blueprint now."
        )

 