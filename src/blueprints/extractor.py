"""
LLM-backed Blueprint extraction (v3).

Wraps a single Sonnet call that turns a scraped TikTok video (caption + transcript +
stats + apidojo metadata) into a validated 16-field two-tier Blueprint. Performs LLM
extraction and persists raw responses to the database for cache reparse.
"""

import hashlib
import json

from src.blueprints.schema import Blueprint, EXTRACTOR_VERSION
from src.models.trend import RawContentItem
from src.models.extractor_response import ExtractorResponse
from src.observability.tracing import traced
from src.providers.llm.anthropic_llm import AnthropicLLM

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

SYSTEM_PROMPT = """You are an expert AI visual content analyst specializing in TikTok virality mechanics.
Your job is to extract a structured Blueprint from a scraped TikTok video.

You receive: caption, optional transcript, hashtags, author handle, duration,
view/like/comment/share/save counts, music metadata, the originating hashtag,
optional location signal, a music_is_original flag, and a niche label.

== TIER 1 FIELDS (universal mechanics) ==
Describe what IS, not how good it is. No quality scoring.
All 8 Tier 1 categorical fields below (hook_type, share_hook_type, comment_bait_type, pacing, loop_type, audio_type,
visual_complexity, color_mood) are locked enums. You MUST pick exactly one value from the Field Reference at the
bottom of this prompt for each. Inventing a new value will fail validation.

hook_type: what the first 1-2 seconds do to stop the scroll.

share_hook_type: observable property of the video that makes viewers want to share it (not viewer motive).

comment_bait_type: observable property that invites comments.

pacing: edit rhythm felt by the viewer.

loop_type: how/whether the video loops.

audio_type: dominant audio character.

visual_complexity: density of information on screen.

color_mood: dominant color palette feeling.

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

== FIELD REFERENCE ==
Use exactly one of the listed values per field. If no value fits well, pick the closest match — do not invent new values.

hook_type — opening device that stops scroll
  - visual_shock — first frame is visually impossible, jarring, or breaks expectations
  - identity_signal — "this is for people like me" — niche/in-group recognition cue
  - curiosity_gap — opens a question viewer needs answered, withholds payoff
  - uncanny_reveal — slow drip of wrongness or unease, viewer leans in to figure out what's off
  - nostalgia_trigger — references shared memory, era, or aesthetic from viewer's past

share_hook_type — reason viewer sends to a friend
  - technical_awe — "look how it's made" — process or craft impressiveness
  - shocking — "you have to see this" — disbelief reaction
  - identity_signal — "this is so us" — affirms shared identity with recipient
  - makes_friends_laugh — pure humor, expected shared laugh

comment_bait_type — mechanic that triggers comments
  - relatable_moment — shared experience prompts "this is literally me"
  - controversial_claim — disagreement bait, invites debate
  - open_ending — unresolved finish, viewers fill in the gap
  - question_to_viewer — direct prompt, asks for opinion or experience

pacing — edit rhythm
  - moderate — balanced cut rate, conversational tempo
  - slow_atmospheric — long shots, minimal cuts, builds mood
  - fast — rapid cuts, high-energy edits

loop_type — how video ends back at start
  - none — clean ending, no loop intent
  - hard_cut — abrupt cut back, jarring loop
  - seamless_visual — last frame matches first, invisible loop
  - narrative_loop — story ending sets up the beginning thematically

audio_type — sound source
  - trending_audio — uses platform-trending sound or song
  - original_voiceover — creator-recorded narration
  - ambient_sfx — sound effects and environment audio, no music
  - music_only — instrumental track, no voice

visual_complexity — density of on-screen elements
  - moderate — balanced composition, clear subject + supporting elements
  - minimal — single focal subject, lots of negative space
  - dense — many elements competing for attention, busy frame

color_mood — dominant color treatment
  - vivid_saturated — high-chroma, punchy colors
  - desaturated — muted, low-chroma palette
  - warm_muted — warm tones at low saturation
  - cool_clinical — cool tones, sterile feel
  - neon — fluorescent, glowing color blocks
"""

def build_envelope(item: RawContentItem, transcript_text: str | None, niche_label: str) -> str:
    """Build LLM prompt envelope from a scraped item. Pure function — no LLM call, no DB write.
    
    Extracted from BlueprintExtractor for reuse by dry-run cost estimator and future
    indexers. 
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
        f"Extract the {EXTRACTOR_VERSION} Blueprint now. Set extractor_version='{EXTRACTOR_VERSION}' and "
        f"extractor_model='claude-sonnet-4-6'. Set niche_label='{niche_label}'."
    )

def compute_prompt_fingerprint(system_prompt: str, envelope: str, model: str, sampling_params: dict) -> str:
    """
    Compute a deterministic SHA-256 fingerprint of a prompt configuration.

    Used to key cached LLM responses by the exact prompt inputs that produced them.
    Same inputs always produce the same fingerprint; any change produces a different one.
    Dict key order is normalized (sorted), so {"a":1, "b":2} and {"b":2, "a":1} hash identically.

    Args:
        system_prompt: System prompt text.
        envelope: Per-request user message / context.
        model: Model name (e.g. "claude-sonnet-4-6").
        sampling_params: Dict of sampling parameters (temperature, max_tokens, etc.).

    Returns:
        SHA-256 hex digest (64 chars).
    """
    data = {
        "system_prompt": system_prompt,
        "envelope": envelope,
        "model": model,
        "sampling_params": sampling_params,
    }
    serialized = json.dumps(data, sort_keys=True)
    bytes_to_hash = serialized.encode()
    return hashlib.sha256(bytes_to_hash).hexdigest()

class BlueprintExtractor:
    """
    Extracts v3 Blueprints from scraped TikTok videos and caches raw LLM responses.

    Each extract() call persists the model's raw output to extractor_responses, keyed
    by (content_item_id, prompt_fingerprint). Future schema bumps can re-validate cached
    responses via reparse_from_cache() without re-calling the API.
    """

    def __init__(self, llm: AnthropicLLM | None = None):
        self.llm = llm or AnthropicLLM(model="claude-sonnet-4-6")

    @traced(name="blueprints.extract", kind="generation")
    def extract(self, item: RawContentItem, transcript_text: str | None, niche_label: str, db: Session) -> Blueprint:
        """Extract a v3 Blueprint from a scraped video item and cache the raw LLM response.

        Args:
            item: RawContentItem with metadata fields populated.
            transcript_text: Plain text transcript from subtitles, or None if unavailable.
            niche_label: String matching niches.name (e.g. "surreal_hyperreal").
            db: SQLAlchemy session used to persist the raw LLM response. Duplicate
                (same item + same prompt fingerprint) is silently ignored.

        Returns:
            Validated Blueprint object. Notes will flag low confidence if transcript missing.
        """
        envelope = build_envelope(item, transcript_text, niche_label)

        blueprint, raw_meta = self.llm.parse_with_raw(
            prompt=envelope,
            response_model=Blueprint,
            system=SYSTEM_PROMPT,
            max_tokens=2048,
        )

        sampling_params = {"max_tokens": 2048}
        fingerprint = compute_prompt_fingerprint(SYSTEM_PROMPT, envelope, self.llm.model, sampling_params)

        row = ExtractorResponse(
            content_item_id=item.id,
            prompt_fingerprint=fingerprint,
            system_prompt=SYSTEM_PROMPT,
            envelope=envelope,
            raw_response=raw_meta["raw_response"],
            model=self.llm.model,
            usage_input_tokens=raw_meta.get("usage_input_tokens"),
            usage_output_tokens=raw_meta.get("usage_output_tokens"),
            usage_cache_read_tokens=raw_meta.get("usage_cache_read_tokens"),
            usage_cache_write_tokens=raw_meta.get("usage_cache_write_tokens"),
        )

        try: 
            db.add(row)
            db.flush()
        except IntegrityError:
            # Duplicate (content_item_id, prompt_fingerprint) is expected if extract()
            # is called twice on the same item with identical prompt config. Silently
            # ignore to maintain idempotency for batch re-runs.
            db.rollback()
            
        return blueprint

    
    def reparse_from_cache(
        self,
        item: RawContentItem,
        transcript_text: str | None,
        niche_label: str,
        db: Session,
    ) -> Blueprint | None:
        """Re-validate a cached raw LLM response through the current Blueprint schema.

        Builds the same envelope + fingerprint that extract() would produce, looks up
        the matching extractor_responses row, and runs model_validate on the stored dict.
        No LLM call is made — this is a pure schema re-parse from cached data.

        Args:
            item: RawContentItem to look up in the cache.
            transcript_text: Same transcript that would be passed to extract(). Required
                to reproduce the identical envelope and thus the correct fingerprint.
            niche_label: Same niche label that would be passed to extract().
            db: SQLAlchemy session for the cache lookup query.

        Returns:
            Validated Blueprint if a cached response exists for the current prompt fingerprint.
            None if no cached row is found (cache miss — caller should call extract() instead).

        Raises:
            pydantic.ValidationError: If a cached row exists but its raw_response dict is
                invalid under the current Blueprint schema. Propagated so the caller can
                surface the failure rather than silently falling back to a re-call.
        """
        envelope = build_envelope(item, transcript_text, niche_label)
        fingerprint = compute_prompt_fingerprint(SYSTEM_PROMPT, envelope, self.llm.model, {"max_tokens": 2048})

        resp = db.execute(
            select(ExtractorResponse).filter_by(
                content_item_id=item.id, prompt_fingerprint=fingerprint
            )
        ).scalar_one_or_none()

        if resp is None:
            return None

        return Blueprint.model_validate(resp.raw_response)

    def extract_or_reparse(
        self,
        item: RawContentItem,
        transcript_text: str | None,
        niche_label: str,
        db: Session,
    ) -> Blueprint:
        """Return a Blueprint using cached raw response if available, otherwise call the LLM.

        Tries reparse_from_cache() first. Falls back to extract() on cache miss.
        Always returns a Blueprint — never returns None.

        Args:
            item: RawContentItem with metadata fields populated.
            transcript_text: Plain text transcript from subtitles, or None if unavailable.
            niche_label: String matching niches.name (e.g. "surreal_hyperreal").
            db: SQLAlchemy session for cache lookup and raw response persistence.

        Returns:
            Validated Blueprint object.
        """
        blueprint = self.reparse_from_cache(item, transcript_text, niche_label, db)

        if blueprint is not None:
            return blueprint
        
        return self.extract(item, transcript_text, niche_label, db)