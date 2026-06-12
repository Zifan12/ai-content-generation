"""
Deterministic ("code-check") rubric criteria for the P3 writer (v0).

Each criterion is a PURE function: it takes a ContentPackage and returns a
CheckResult receipt — no LLM, no I/O. These catch MECHANICAL doctrine violations
(mood drift, scale words, quality incantations, palette/style leaks, missing
event end-frame) that a string-compare can verify with 100% reliability, before
any paid render. Judgment calls (vantage, anti-causal) are NOT here — those are
the v1 LLM-judge tier.

A failing receipt's `reason` must name WHAT failed (which shot, which banned
word) — the receipt is the whole point.
"""

import re
from dataclasses import dataclass

from src.schemas.generation import ContentPackage


@dataclass
class CheckResult:
    """
    One criterion's verdict on one package — the receipt a check hands back.

    Attributes:
      criterion_id: Which rule was checked (e.g. "mood_anchor_identical").
      passed: True if the package obeys the rule, False if it violates it.
      reason: On failure, names exactly what broke (which shot, which word) so the
        scorecard reads as a receipt, not a bare boolean. On pass, a short "ok".
    """

    criterion_id: str
    passed: bool
    reason: str

def no_scale_comparison(package: ContentPackage) -> CheckResult:
    """
    Fail if any keyframe or motion text contains a literal size-comparison.

    Scale clichés ("thick as a ship's mast", "size of a building") are a recurring
    writer tic that reads as fake. This catches the cheap, repeating phrasings
    cheaply; novel phrasings are the v1 judge's job. Scans every shot's
    start_keyframe (when present — only segment 1 has one), end_keyframe (when
    present), and motion, case-insensitively.
    On the first banned phrase found, returns a failing receipt naming the phrase
    and the shot; if none match, passes.
    """
    banned = [
        "thick as",
        "size of a",
        "size of an",
        "as big as",
        "as large as",
        "as tall as",
        "as wide as",
        "like a building",
        "like a cathedral",
        "like a skyscraper",
        "like a tower",
        "like a mountain",
    ]
    for i, shot in enumerate(package.shots, start=1):
        fields = [shot.start_keyframe, shot.end_keyframe, shot.motion]
        for text in fields:
            if text is None:
                continue
            lowered = text.lower()
            for phrase in banned:
                if phrase in lowered:
                    return CheckResult(
                        criterion_id="no_scale_comparison",
                        passed=False,
                        reason=f"shot {i} contains scale comparison: {phrase!r}",
                    )
    return CheckResult(
        criterion_id="no_scale_comparison",
        passed=True,
        reason="no scale comparisons found",
    )


def no_quality_incantations(package: ContentPackage) -> CheckResult:
    """
    Fail if any text field contains a dead "quality" word.

    Words like "masterpiece", "8k", "breathtaking" are cargo-cult prompt filler —
    they do nothing for a modern model and read as AI slop. They leak into captions
    and keyframes alike, so this scans every text surface present on each shot:
    start_keyframe (segment 1 only), motion (always), and end_keyframe (when set),
    plus the caption and (when present) the voiceover. Matching is case-insensitive
    and WHOLE-WORD (regex word
    boundaries) so "8k" does not fire on "8kg" and "stunning" is not matched inside
    a longer token. Collects every distinct hit and, if any, returns a failing
    receipt listing them; otherwise passes.
    """
    banned = [
        "masterpiece",
        "8k",
        "ultra-detailed",
        "ultra detailed",
        "stunning",
        "breathtaking",
        "flawless",
        "hyperrealistic",
    ]
    texts: list[str] = [package.caption]
    if package.voiceover is not None:
        texts.append(package.voiceover)
    for shot in package.shots:
        if shot.start_keyframe is not None:
            texts.append(shot.start_keyframe)
        texts.append(shot.motion)
        if shot.end_keyframe is not None:
            texts.append(shot.end_keyframe)

    blob = " ".join(texts).lower()
    hits = [word for word in banned if re.search(rf"\b{re.escape(word)}\b", blob)]
    if hits:
        return CheckResult(
            criterion_id="no_quality_incantations",
            passed=False,
            reason=f"quality incantations present: {hits}",
        )
    return CheckResult(
        criterion_id="no_quality_incantations",
        passed=True,
        reason="no quality incantations found",
    )


def no_palette_in_keyframes(package: ContentPackage) -> CheckResult:
    """
    Fail if any generated keyframe carries palette / grade vocabulary (severity: warn).

    The grade lives in mood_anchor (appended verbatim to every keyframe to lock the
    look); a keyframe that also names colors/grade double-specifies it and can fight
    the anchor. This is a HEURISTIC — false positives are acceptable, so the word
    list is intentionally loose and kept inline. Scans both generated frames of each
    shot — start_keyframe and end_keyframe — case-insensitively, skipping any that
    are None (segments 2-3 inherit the prior clip's last frame and carry no
    start_keyframe). Each present frame is run through the palette-word list plus a
    regex for hex color codes (#RRGGBB). motion is out of scope here (covered by
    no_style_words_in_motion). First hit returns a failing receipt naming the shot
    and the offending token; otherwise passes.
    """
    palette_words = [
        "palette",
        "grade",
        "teal and orange",
        "saturated",
        "monochromatic",
    ]
    hex_pattern = re.compile(r"#[0-9a-fA-F]{6}\b")
    for i, shot in enumerate(package.shots, start=1):
        fields = [shot.start_keyframe, shot.end_keyframe]
        for text in fields:
            if text is None:
                continue
            lowered = text.lower()
            for word in palette_words:
                if word in lowered:
                    return CheckResult(
                        criterion_id="no_palette_in_keyframes",
                        passed=False,
                        reason=f"shot {i} keyframe carries palette vocab: {word!r}",
                    )
            hex_match = hex_pattern.search(text)
            if hex_match is not None:
                return CheckResult(
                    criterion_id="no_palette_in_keyframes",
                    passed=False,
                    reason=f"shot {i} keyframe carries hex color: {hex_match.group()!r}",
                )
    return CheckResult(
        criterion_id="no_palette_in_keyframes",
        passed=True,
        reason="no palette vocabulary in any keyframes",
    )


def no_style_words_in_motion(package: ContentPackage) -> CheckResult:
    """
    Fail if any motion field contains style / aesthetic words (severity: warn).

    A motion field describes ONE movement (push-in, drift, shimmer) — it should carry
    no aesthetic adjectives; those belong in mood_anchor. "slow cinematic push-in"
    smuggles a look word into a motion field. HEURISTIC, false positives acceptable;
    word list kept inline. Scans only each shot's motion, case-insensitively. First
    hit returns a failing receipt naming the shot and the word; else passes.
    """
    style_words = [
        "cinematic",
        "moody",
        "dreamlike",
        "aesthetic",
        "style",
        "grade",
        "vibe",
    ]
    for i, shot in enumerate(package.shots, start=1):
        lowered = shot.motion.lower()
        for word in style_words:
            if word in lowered:
                return CheckResult(
                    criterion_id="no_style_words_in_motion",
                    passed=False,
                    reason=f"shot {i} motion carries style word: {word!r}",
                )
    return CheckResult(
        criterion_id="no_style_words_in_motion",
        passed=True,
        reason="no style words in any transition",
    )


def device_requires_event_beat(package: ContentPackage) -> CheckResult:
    """
    Fail if a change-device package promises a visible change but no shot delivers one
    (severity: error).

    Two devices — transformation and time_compression — are change-devices: their
    whole render mechanism IS the keyframe pair (a start frame and an end frame that
    differ), so the model can interpolate the visible change between them. A package
    on one of those devices that has no end_keyframe anywhere is incoherent: it claims
    a change the render layer cannot produce. The event beat is the presence of at
    least one end_keyframe. This check is only meaningful for the two change-devices;
    the rubric's select() gates it so it runs solely for those (other devices never
    reach here). Passes when at least one shot carries an end_keyframe; otherwise
    returns a failing receipt naming the device.
    """
    has_event = any(shot.end_keyframe is not None for shot in package.shots)
    if has_event:
        return CheckResult(
            criterion_id="device_requires_event_beat",
            passed=True,
            reason="at least one shot has an end_keyframe (event beat present)",
        )
    return CheckResult(
        criterion_id="device_requires_event_beat",
        passed=False,
        reason=f"device {package.device!r} promises a visible change but no segment has an end_keyframe",
    )

