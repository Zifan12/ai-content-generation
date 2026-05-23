import hashlib
from typing import Any
from src.miner.schemas import BlueprintCandidate

def _blueprint_lines(blueprint_data: dict[str, Any]) -> list[str]:
    
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

    return "\n".join(_blueprint_lines(candidate.blueprint_template))

    
def embed_text_hash(text: str) -> str:
    """Return first 16 hex chars of SHA-256 for serialized embed text."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]

