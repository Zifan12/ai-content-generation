"""Blueprint-aware embed-input serialization for P2 RAG.

Single source of truth for the string fed to the BGE-M3 embedder.
Both the indexer (writes `viral_videos.embedding`) and the retriever
(embeds `BlueprintCandidate` queries) call into here — drift between
the two sides lands vectors in different subspaces and breaks
retrieval silently. Hash via `embed_text_hash` keys the indexer's
invalidation cache.
"""

import hashlib
from typing import Any
from src.miner.schemas import BlueprintCandidate

def _blueprint_lines(blueprint_data: dict[str, Any]) -> list[str]:
    """Return one labeled line per populated Blueprint field, in locked order.

    Order: aesthetic → hook (+ optional subtype) → emotion → pacing → audio → mood.
    Order and labels are part of the embed contract — never reorder, never rename;
    both index-side and query-side serializers depend on byte-identical output for
    the same input. Missing or empty fields skip their line entirely (no blank
    `field:` emissions, which would drift the hash).

    Args:
        blueprint_data: dict with any subset of the 6 embed-relevant Blueprint fields.
            May be a full v3.1 Blueprint or a sparse `BlueprintCandidate.blueprint_template`.

    Returns:
        List of formatted lines, one per field that had a truthy value.
    """
    lines = []

    aesthetic = blueprint_data.get("aesthetic_descriptors")
    if aesthetic:
        lines.append("aesthetic: " + ", ".join(aesthetic))

    hook_type = blueprint_data.get("hook_type")
    if hook_type:
        hook_subtype  = blueprint_data.get("hook_subtype")
        if hook_subtype:
            lines.append(f"hook: {hook_type} / {hook_subtype}")
        else:
            lines.append(f"hook: {hook_type}")
    
    emotion = blueprint_data.get("primary_emotion")
    if emotion:
        lines.append(f"emotion: {emotion}")

    pacing = blueprint_data.get("pacing")
    if pacing:
        lines.append(f"pacing: {pacing}")

    audio = blueprint_data.get("audio_type")
    if audio:
        lines.append(f"audio: {audio}")

    mood = blueprint_data.get("color_mood")
    if mood:
        lines.append(f"mood: {mood}")

    return lines


def serialize_for_embed(
    *,
    description: str | None,
    hashtags: list[str] | None,
    transcript: str | None,
    blueprint_data: dict[str, Any],
) -> str:
    """Build the canonical embed-input string for one indexed video.

    Combines raw video text (description, hashtags, transcript) with the
    structured Blueprint fields produced by the extractor. Lines emitted in
    locked order: description → hashtags → transcript → Blueprint lines.
    Any input that is None or empty is skipped — never emits a blank
    `field:` line (would drift the embed-text hash).

    Args:
        description: TikTok caption text, or None.
        hashtags: List of tag tokens (separator is a single space at join time), or None.
        transcript: Full subtitle text, or None when no subtitles available.
        blueprint_data: v3.1 Blueprint dict pulled from `blueprints.blueprint_data`.

    Returns:
        Single `\\n`-joined string ready for `BgeM3Embedder.embed(...)`.
    """
    lines = []

    if description:
        lines.append(f"description: {description}")

    if hashtags:
        lines.append(f"hashtags: {' '.join(hashtags)}")

    if transcript:
        lines.append(f"transcript: {transcript}")
    
    
    lines.extend(_blueprint_lines(blueprint_data))

    return "\n".join(lines)


def serialize_candidate_for_query(candidate: BlueprintCandidate) -> str:
    """Build the canonical embed-input string for one retrieval query.

    The retriever takes a ranked mechanic combo from the miner (a
    `BlueprintCandidate`) and uses it as the query against the indexed
    `viral_videos` corpus. Query-side has no raw video text by design —
    `blueprint_template` holds only the mechanic fields the miner grouped
    on. Output is therefore a strict subset of what `serialize_for_embed`
    produces for the same Blueprint dict with all raw-text inputs None.

    Args:
        candidate: Ranked mechanic combo with `blueprint_template` dict.

    Returns:
        Single `\\n`-joined string ready for `BgeM3Embedder.embed(...)`.
    """
    return "\n".join(_blueprint_lines(candidate.blueprint_template))

    
def embed_text_hash(text: str) -> str:
    """Return a 16-char SHA-256 prefix used as the indexer's cache key.

    Stored alongside each `viral_videos.embedding` row. Re-index only when
    the hash for the current serialized text differs from the stored one —
    lets the indexer skip re-embedding unchanged rows. Length is fixed at
    16 hex chars (64 bits of entropy, low collision risk at corpus scale
    <1M items).
    """
    return hashlib.sha256(text.encode()).hexdigest()[:16]

