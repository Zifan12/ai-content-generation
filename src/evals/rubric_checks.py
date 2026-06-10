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


def mood_anchor_identical(package: ContentPackage) -> CheckResult:
    """Fail unless all three shots carry a byte-identical mood_anchor (the grade-lock invariant)."""

    s1, s2, s3 = package.shots[0].mood_anchor, package.shots[1].mood_anchor, package.shots[2].mood_anchor
        
    if s1 == s2 == s3:
        return CheckResult(criterion_id="mood_anchor_identical", passed=True, reason="all three mood_anchors identical")
    return  CheckResult(criterion_id="mood_anchor_identical", passed=False, reason="all three mood_anchors differ")


def no_scale_comparison(package: ContentPackage) -> CheckResult:
    """
    Fail if any keyframe or transition text contains a literal size-comparison.

    Scale clichés ("thick as a ship's mast", "size of a building") are a recurring
    writer tic that reads as fake. This catches the cheap, repeating phrasings
    cheaply; novel phrasings are the v1 judge's job. Scans every shot's
    start_keyframe, end_keyframe (when present), and transition, case-insensitively.
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
        fields = [shot.start_keyframe, shot.end_keyframe, shot.transition]
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
    and keyframes alike, so this scans every text surface: all three shots'
    start_keyframe / end_keyframe / transition, plus the caption and (when present)
    the voiceover. Matching is case-insensitive and WHOLE-WORD (regex word
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
        texts.append(shot.start_keyframe)
        texts.append(shot.transition)
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


def no_palette_in_start_keyframe(package: ContentPackage) -> CheckResult:
    """
    Fail if any start_keyframe carries palette / grade vocabulary (severity: warn).

    The grade lives in mood_anchor (appended verbatim to every keyframe to lock the
    look); a start_keyframe that also names colors/grade double-specifies it and can
    fight the anchor. This is a HEURISTIC — false positives are acceptable, so the
    word list is intentionally loose and kept inline. Scans only the start_keyframe
    of each shot (end_keyframe/transition are out of scope here), case-insensitively,
    plus a regex for hex color codes (#RRGGBB). First hit returns a failing receipt
    naming the shot and the offending token; otherwise passes.
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
        lowered = shot.start_keyframe.lower()
        for word in palette_words:
            if word in lowered:
                return CheckResult(
                    criterion_id="no_palette_in_start_keyframe",
                    passed=False,
                    reason=f"shot {i} start_keyframe carries palette vocab: {word!r}",
                )
        hex_match = hex_pattern.search(shot.start_keyframe)
        if hex_match is not None:
            return CheckResult(
                criterion_id="no_palette_in_start_keyframe",
                passed=False,
                reason=f"shot {i} start_keyframe carries hex color: {hex_match.group()!r}",
            )
    return CheckResult(
        criterion_id="no_palette_in_start_keyframe",
        passed=True,
        reason="no palette vocabulary in any start_keyframe",
    )


def no_style_words_in_transition(package: ContentPackage) -> CheckResult:
    """
    Fail if any transition contains style / aesthetic words (severity: warn).

    A transition describes ONE motion (push-in, drift, shimmer) — it should carry no
    aesthetic adjectives; those belong in mood_anchor. "slow cinematic push-in"
    smuggles a look word into a motion field. HEURISTIC, false positives acceptable;
    word list kept inline. Scans only each shot's transition, case-insensitively.
    First hit returns a failing receipt naming the shot and the word; else passes.
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
        lowered = shot.transition.lower()
        for word in style_words:
            if word in lowered:
                return CheckResult(
                    criterion_id="no_style_words_in_transition",
                    passed=False,
                    reason=f"shot {i} transition carries style word: {word!r}",
                )
    return CheckResult(
        criterion_id="no_style_words_in_transition",
        passed=True,
        reason="no style words in any transition",
    )


def escalating_wrongness_has_event_beat(package: ContentPackage) -> CheckResult:
    """
    Fail if no shot has an end_keyframe set (conditional — escalating_wrongness only).

    The escalating_wrongness principle promises the wrongness visibly ADVANCES — that
    needs at least one EVENT beat (a shot with both start_keyframe and end_keyframe,
    so the renderer can interpolate the A->B change). A package that claims this
    principle but gives only idle stills (every end_keyframe None) never escalates.
    The selector only fires this criterion when organizing_principle ==
    "escalating_wrongness"; the function itself just checks: does any shot carry a
    non-None end_keyframe? Passes if yes, fails if none.
    """
    has_event = any(shot.end_keyframe is not None for shot in package.shots)
    if has_event:
        return CheckResult(
            criterion_id="escalating_wrongness_has_event_beat",
            passed=True,
            reason="at least one shot has an end_keyframe (event beat present)",
        )
    return CheckResult(
        criterion_id="escalating_wrongness_has_event_beat",
        passed=False,
        reason="no shot has an end_keyframe — escalating_wrongness has no event beat",
    )