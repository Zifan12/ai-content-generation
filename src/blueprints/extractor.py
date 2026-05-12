"""
LLM-backed Blueprint extraction (v3).

Wraps a single Sonnet call that turns a scraped TikTok video (caption + transcript +
stats + apidojo metadata) into a validated 16-field two-tier Blueprint. Pure compute —
persistence lives in the batch CLI script that drives this class.
"""

from src.blueprints.schema import Blueprint
from src.models.trend import RawContentItem
from src.observability.tracing import traced
from src.providers.llm.anthropic_llm import AnthropicLLM


SYSTEM_PROMPT = """You are an expert AI visual content analyst specializing in TikTok virality mechanics.
Your job is to extract a structured Blueprint from a scraped TikTok video.

You receive: caption, optional transcript, hashtags, author handle, duration,
view/like/comment/share/save counts, music metadata, the originating hashtag,
optional location signal, a music_is_original flag, and a niche label.

== TIER 1 FIELDS (universal mechanics) ==
Emit short snake_case values. Prefer terse 1-3 word labels. No quality scoring — describe what IS, not how good it is.

hook_type: what the first 1-2 seconds do to stop the scroll.
  Examples: "curiosity_gap", "visual_shock", "pattern_interrupt", "identity_signal", "uncanny_reveal"

share_hook_type: observable property of the video that makes viewers want to share it (not viewer motive).
  Examples: "shocking", "identity_signal", "technical_awe", "makes_friends_laugh"

comment_bait_type: observable property that invites comments.
  Examples: "question_to_viewer", "controversial_claim", "relatable_moment", "open_ending"

pacing: edit rhythm felt by the viewer.
  Examples: "fast", "slow_atmospheric", "moderate", "chaotic_cuts"

loop_type: how/whether the video loops.
  Examples: "seamless_visual", "narrative_loop", "hard_cut", "none"

audio_type: dominant audio character.
  Examples: "original_voiceover", "trending_audio", "ambient_sfx", "music_only", "silent"

visual_complexity: density of information on screen.
  Examples: "minimal", "moderate", "dense", "overwhelming"

color_mood: dominant color palette feeling.
  Examples: "desaturated", "vivid_saturated", "neon", "warm_muted", "cool_clinical"

primary_emotion: the primary emotion the video triggers. Must be exactly one of:
  awe | surprise | tension | humor | anger | anxiety | aspiration | satisfaction | relatability

duration_band: video length bucket. Must be exactly one of:
  under_10s | 10_20s | 20_40s | 40_60s | over_60s

== TIER 2 FIELDS (niche-conditional) ==
aesthetic_descriptors: 3-6 free-text snake_case tags capturing visual/tonal identity.
  Be specific (e.g. "photorealistic", "impossible_physics", "liminal_space", "uncanny_proportions").
  Not generic ("nice", "cool"). Niche-specific vocabulary is fine — normalized later.

niche_label: echo back the niche label you were given. Do not infer or change it.

hook_subtype: optional secondary hook descriptor if the hook has a notable sub-pattern. Null if not applicable.

== METADATA ==
Set extractor_version and extractor_model exactly as instructed in the prompt.
Use notes for uncertainty. Never refuse — always output a complete Blueprint.
"""


class BlueprintExtractor:
    """One-shot LLM extraction of a v3 Blueprint from a RawContentItem + optional transcript.

    Builds a text envelope from video metadata, sends it to Sonnet via AnthropicLLM.parse,
    and returns a validated Blueprint Pydantic object. Does not touch the database —
    persistence is the caller's responsibility (see scripts/extract_blueprints.py).
    """

    def __init__(self, llm: AnthropicLLM | None = None):
        self.llm = llm or AnthropicLLM(model="claude-sonnet-4-6")

    @traced(name="blueprints.extract", kind="generation")
    def extract(
        self,
        item: RawContentItem,
        transcript_text: str | None,
        niche_label: str,
    ) -> Blueprint:
        """Extract a v3 Blueprint from a scraped video item.

        Args:
            item: RawContentItem with metadata fields populated.
            transcript_text: Plain text transcript from subtitles, or None if unavailable.
            niche_label: String matching niches.name (e.g. "surreal_hyperreal").
                Threaded into the envelope as runtime metadata; LLM echoes it back.

        Returns:
            Validated Blueprint object. Notes will flag low confidence if transcript missing.
        """
        envelope = self._build_envelope(item, transcript_text, niche_label)

        return self.llm.parse(
            prompt=envelope,
            response_model=Blueprint,
            system=SYSTEM_PROMPT,
            max_tokens=2048,
        )

    def _build_envelope(
        self,
        item: RawContentItem,
        transcript_text: str | None,
        niche_label: str,
    ) -> str:
        """Build text envelope from v3 video metadata + optional transcript.

        Args:
            item: RawContentItem with apidojo v3 fields populated.
            transcript_text: Plain text transcript, or None if unavailable.
            niche_label: Niche string to include as context and require LLM to echo.

        Returns:
            Formatted prompt string containing all video context for Blueprint extraction.
        """
        transcript_block = (
            f"Transcript:\n{transcript_text}"
            if transcript_text
            else "Transcript: (missing)"
        )

        hashtags = ", ".join(item.hashtags) if item.hashtags else "(none)"

        music_is_original = item.music_is_original
        if music_is_original is None:
            music_flag = "unknown"
        elif music_is_original:
            music_flag = "true (original sound by this author)"
        else:
            music_flag = "false (likely trending/meme audio)"

        source_line = (
            f"Originating hashtag URL: {item.input_source}"
            if item.input_source
            else "Originating hashtag URL: (unknown)"
        )

        poi_line = (
            f"Location signal: {item.poi_name}"
            if item.poi_name
            else "Location signal: (none)"
        )

        return (
            f"Niche label: {niche_label}\n"
            f"Author: {item.author_username or '(unknown)'}\n"
            f"Duration: {item.duration_in_seconds or 'unknown'} seconds\n"
            f"Views: {item.views:,} | Likes: {item.likes:,} | "
            f"Comments: {item.comments:,} | Shares: {item.shares:,} | "
            f"Saves: {item.collect_count or 0:,}\n"
            f"Hashtags: {hashtags}\n"
            f"{source_line}\n"
            f"{poi_line}\n"
            f"Music is original: {music_flag}\n\n"
            f"Caption / Description:\n{item.description or '(no caption)'}\n\n"
            f"{transcript_block}\n\n"
            f"Extract the v3 Blueprint now. Set extractor_version='v3' and "
            f"extractor_model='claude-sonnet-4-6'. Set niche_label='{niche_label}'."
        )
